"""Customer Support ticket statuses: the database, API and UI agree on the
seven canonical statuses (migration c7d8e9f0a1b2 added 'assigned' and
'waiting_for_customer'), and anything else is rejected clearly."""
import uuid

import pytest
from sqlalchemy import text

from config.database import engine
from modules.customer_support.schemas import TicketStatus

BASE = "/api/v1/customer-support/tickets"
CANONICAL = ["open", "assigned", "in_progress", "waiting_for_customer", "resolved", "closed", "escalated"]


def _ticket(client, headers):
    categories = client.get("/api/v1/customer-support/categories", headers=headers).json()
    r = client.post(BASE, headers=headers, json={
        "subject": f"Status check {uuid.uuid4().hex[:8]}", "description": "Ticket status regression test.",
        "priority": "medium", "category_id": categories[0]["id"] if categories else None, "channel": "web",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_database_enum_matches_api_and_model():
    with engine.connect() as conn:
        labels = [r[0] for r in conn.execute(text(
            "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'support_ticket_status' ORDER BY enumsortorder"
        ))]
    assert labels == CANONICAL
    assert list(TicketStatus.__args__) == CANONICAL


@pytest.mark.parametrize("new_status", CANONICAL)
def test_every_canonical_status_can_be_saved_and_read_back(client, new_user, new_status):
    owner = new_user("Status Owner", role="employee")
    agent = new_user("Status Agent", role="support_agent")
    ticket_id = _ticket(client, owner["headers"])
    r = client.put(f"{BASE}/{ticket_id}", headers=agent["headers"], json={"status": new_status})
    assert r.status_code == 200, r.text
    assert client.get(f"{BASE}/{ticket_id}", headers=owner["headers"]).json()["status"] == new_status
    filtered = client.get(BASE, headers=agent["headers"], params={"status": new_status, "limit": 100}).json()
    assert ticket_id in [t["id"] for t in filtered]


def test_unsupported_status_is_rejected_clearly(client, new_user):
    owner = new_user("Status Owner", role="employee")
    agent = new_user("Status Agent", role="support_agent")
    ticket_id = _ticket(client, owner["headers"])
    r = client.put(f"{BASE}/{ticket_id}", headers=agent["headers"], json={"status": "pending_vendor"})
    assert r.status_code == 422
    assert "status" in r.text
    assert client.get(f"{BASE}/{ticket_id}", headers=owner["headers"]).json()["status"] == "open"


def test_assigned_and_waiting_count_correctly_in_stats(client, new_user):
    owner = new_user("Status Owner", role="employee")
    agent = new_user("Status Agent", role="support_agent")
    before = client.get("/api/v1/customer-support/stats", headers=agent["headers"]).json()
    assigned_id = _ticket(client, owner["headers"])
    waiting_id = _ticket(client, owner["headers"])
    client.put(f"{BASE}/{assigned_id}", headers=agent["headers"], json={"status": "assigned"})
    client.put(f"{BASE}/{waiting_id}", headers=agent["headers"], json={"status": "waiting_for_customer"})
    after = client.get("/api/v1/customer-support/stats", headers=agent["headers"]).json()
    assert after["total_tickets"] == before["total_tickets"] + 2
    assert after["open_tickets"] == before["open_tickets"] + 1  # 'assigned' counts as open work
    assert after["resolved_tickets"] == before["resolved_tickets"]


def test_status_change_notifies_owner(client, new_user):
    owner = new_user("Status Owner", role="employee")
    agent = new_user("Status Agent", role="support_agent")
    ticket_id = _ticket(client, owner["headers"])
    client.put(f"{BASE}/{ticket_id}", headers=agent["headers"], json={"status": "waiting_for_customer"})
    notes = client.get("/api/v1/customer-support/notifications", headers=owner["headers"]).json()["notifications"]
    assert any(n["target_id"] == str(ticket_id) for n in notes)
