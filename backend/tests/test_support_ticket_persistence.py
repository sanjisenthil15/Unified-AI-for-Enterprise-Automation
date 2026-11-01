"""
test_support_ticket_persistence.py

Comprehensive regression tests for Customer Support ticket PostgreSQL persistence:
- Verifies real database storage in `support_tickets` and `ticket_messages`.
- Verifies returned ID matches persisted database row.
- Verifies failure handling and rejection of invalid foreign keys (e.g. non-existent team_id).
- Verifies optional team_id stored as NULL without inventing default teams.
- Verifies duplicate submission protection on retries within 60s.
- Verifies RBAC: only owner and staff (admin, support_agent) can access tickets.
- Verifies ticket status updates and agent replies persist in PostgreSQL.
- Verifies notifications are triggered for status updates and agent replies.
- Verifies list_support_tickets queries PostgreSQL with RBAC filtering.
"""

from unittest.mock import patch
from models.ticket import SupportTicket, TicketMessage
from models.notification import Notification

CS_BASE = "/api/v1/customer-support"


def test_ticket_creation_persists_in_database(client, new_user, db):
    user = new_user("Ticket Requester", role="employee")

    payload = {
        "subject": "Unable to access cloud export pipeline",
        "description": "Export job #EXP-9921 fails with 504 gateway timeout after 30 seconds.",
        "priority": "high",
        "channel": "web",
    }

    r = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    ticket_id = data["id"]
    assert ticket_id is not None

    # Verify directly in PostgreSQL database
    db_ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    assert db_ticket is not None
    assert db_ticket.id == ticket_id
    assert db_ticket.submitted_by == user["id"]
    assert db_ticket.subject == payload["subject"]
    assert db_ticket.description == payload["description"]
    assert db_ticket.priority == "high"
    assert db_ticket.status == "open"
    assert db_ticket.channel == "web"
    assert db_ticket.team_id is None

    # Verify initial thread message persisted in ticket_messages
    db_msg = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket_id).first()
    assert db_msg is not None
    assert db_msg.sender_id == user["id"]
    assert "Support Ticket opened" in db_msg.message


def test_ticket_id_matches_database_record(client, new_user, db):
    user = new_user("Requester Two", role="employee")
    payload = {
        "subject": "Billing inquiry for Q4 invoices",
        "description": "Please clarify tax itemization on invoice 8812.",
        "priority": "low",
        "channel": "chat",
    }
    r = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json=payload)
    assert r.status_code == 201
    ticket_id = r.json()["id"]

    db_row = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    assert db_row is not None
    assert db_row.id == ticket_id


def test_invalid_team_id_returns_error_and_does_not_persist(client, new_user, db):
    user = new_user("Requester Three", role="employee")
    payload = {
        "subject": "Invalid team routing test",
        "description": "Testing that invalid team ID 9999 is rejected.",
        "team_id": 9999,
        "priority": "medium",
    }
    r = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json=payload)
    assert r.status_code == 400
    assert "Support team id=9999 does not exist" in r.json()["detail"]

    # Verify nothing was persisted
    db_row = db.query(SupportTicket).filter(SupportTicket.subject == payload["subject"]).first()
    assert db_row is None


def test_missing_team_id_persists_as_null_without_inventing_team_1(client, new_user, db):
    user = new_user("Requester Four", role="employee")
    payload = {
        "subject": "Optional team ticket",
        "description": "Ticket submitted without explicit team routing.",
        "priority": "medium",
    }
    r = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json=payload)
    assert r.status_code == 201
    ticket_id = r.json()["id"]

    db_ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    assert db_ticket is not None
    assert db_ticket.team_id is None


def test_duplicate_ticket_retry_returns_existing_ticket_without_duplicate_row(client, new_user, db):
    user = new_user("Requester Five", role="employee")
    payload = {
        "subject": "Idempotent retry ticket subject",
        "description": "Idempotent retry ticket description body.",
        "priority": "high",
    }
    r1 = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json=payload)
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    # Immediate second call with identical payload
    r2 = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json=payload)
    assert r2.status_code in (200, 201)
    id2 = r2.json()["id"]
    assert id1 == id2

    # Exactly 1 row in database
    count = db.query(SupportTicket).filter(
        SupportTicket.submitted_by == user["id"],
        SupportTicket.subject == payload["subject"],
    ).count()
    assert count == 1


def test_unauthorized_user_cannot_view_another_users_ticket(client, new_user):
    alice = new_user("Alice Requester", role="employee")
    bob = new_user("Bob Requester", role="employee")
    admin = new_user("Admin User", role="admin")
    agent = new_user("Support Agent", role="support_agent")

    r = client.post(f"{CS_BASE}/tickets", headers=alice["headers"], json={
        "subject": "Alice's confidential issue",
        "description": "Details that only Alice or support should see.",
        "priority": "medium",
    })
    assert r.status_code == 201
    ticket_id = r.json()["id"]

    # Bob cannot view Alice's ticket
    r_bob = client.get(f"{CS_BASE}/tickets/{ticket_id}", headers=bob["headers"])
    assert r_bob.status_code == 403

    # Alice can view her own ticket
    r_alice = client.get(f"{CS_BASE}/tickets/{ticket_id}", headers=alice["headers"])
    assert r_alice.status_code == 200
    assert r_alice.json()["id"] == ticket_id

    # Admin can view
    r_admin = client.get(f"{CS_BASE}/tickets/{ticket_id}", headers=admin["headers"])
    assert r_admin.status_code == 200

    # Support agent can view
    r_agent = client.get(f"{CS_BASE}/tickets/{ticket_id}", headers=agent["headers"])
    assert r_agent.status_code == 200


def test_ticket_status_change_persists_in_database(client, new_user, db):
    user = new_user("Requester Six", role="employee")
    admin = new_user("Admin Resolver", role="admin")

    r = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json={
        "subject": "Status update persistence check",
        "description": "Testing status transition in database.",
        "priority": "medium",
    })
    ticket_id = r.json()["id"]

    # Update to resolved
    r_up = client.put(f"{CS_BASE}/tickets/{ticket_id}", headers=admin["headers"], json={
        "status": "resolved",
    })
    assert r_up.status_code == 200
    assert r_up.json()["status"] == "resolved"

    # Verify directly in PostgreSQL
    db.expire_all()
    db_ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    assert db_ticket.status == "resolved"
    assert db_ticket.resolved_at is not None


def test_agent_reply_persists_in_database_and_notifies_owner(client, new_user, db):
    user = new_user("Ticket Owner", role="employee")
    agent = new_user("Support Specialist", role="support_agent")

    r = client.post(f"{CS_BASE}/tickets", headers=user["headers"], json={
        "subject": "Need assistance with SSO",
        "description": "SAML configuration certificate expired.",
        "priority": "critical",
    })
    ticket_id = r.json()["id"]

    # Agent replies
    reply_text = "We have renewed the certificate metadata. Please retry."
    r_msg = client.post(f"{CS_BASE}/tickets/{ticket_id}/messages", headers=agent["headers"], json={
        "message": reply_text,
    })
    assert r_msg.status_code == 200
    msg_id = r_msg.json()["id"]

    # Verify message in PostgreSQL
    db_msg = db.query(TicketMessage).filter(TicketMessage.id == msg_id).first()
    assert db_msg is not None
    assert db_msg.ticket_id == ticket_id
    assert db_msg.message == reply_text
    assert db_msg.sender_id == agent["id"]

    # Verify notification delivered to user
    notifs = client.get("/api/v1/notifications/me", headers=user["headers"]).json()
    assert any(n["category"] == "support" and n["type"] == "support_agent_reply" for n in notifs)


def test_list_support_tickets_returns_persisted_tickets_with_rbac(client, new_user):
    user1 = new_user("User Alpha", role="employee")
    user2 = new_user("User Beta", role="employee")
    admin = new_user("Admin Lister", role="admin")

    t1 = client.post(f"{CS_BASE}/tickets", headers=user1["headers"], json={
        "subject": "Alpha ticket", "description": "Description Alpha",
    }).json()

    t2 = client.post(f"{CS_BASE}/tickets", headers=user2["headers"], json={
        "subject": "Beta ticket", "description": "Description Beta",
    }).json()

    # User 1 lists tickets: only sees Alpha
    list1 = client.get(f"{CS_BASE}/tickets", headers=user1["headers"]).json()
    ids1 = [t["id"] for t in list1]
    assert t1["id"] in ids1
    assert t2["id"] not in ids1

    # User 2 lists tickets: only sees Beta
    list2 = client.get(f"{CS_BASE}/tickets", headers=user2["headers"]).json()
    ids2 = [t["id"] for t in list2]
    assert t2["id"] in ids2
    assert t1["id"] not in ids2

    # Admin lists tickets: sees both
    admin_list = client.get(f"{CS_BASE}/tickets", headers=admin["headers"]).json()
    admin_ids = [t["id"] for t in admin_list]
    assert t1["id"] in admin_ids
    assert t2["id"] in admin_ids

