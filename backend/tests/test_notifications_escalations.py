"""Phase 4.4 — centralized notifications (categories, entity refs,
dedupe, unread counts, mark-all-read) and the idempotent escalation sweep."""
import uuid
from datetime import datetime, timedelta, timezone

from config.database import SessionLocal
from config.settings import settings
from models.escalation import Escalation
from models.leave_request import LeaveRequest
from models.notification import Notification
from modules.escalations import service as escalation_service
from modules.notifications.service import category_for_type, create_notification
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
NOTIF = "/api/v1/notifications"
REQUESTS = "/api/v1/leave/requests"


def _email(tag):
    return f"pytest_{tag}_{uuid.uuid4().hex[:8]}@example.com"


def _onboard(client, admin_headers, role="employee", full_name="Notif Tester"):
    email = _email("nt")
    roles = client.get("/api/v1/auth/roles", headers=admin_headers).json()
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": full_name, "email": email, "role_id": next(x["id"] for x in roles if x["name"] == role),
        "job_title": "Engineer", "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    headers = complete_first_login(client, email, r.json()["temporary_password"])
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return {"user_id": me["id"], "headers": headers, "employee_id": r.json()["employee"]["id"]}


# ------------------------------------------------------------------ notifications

def test_category_mapping_covers_existing_types():
    assert category_for_type("task_assigned") == "sprint"
    assert category_for_type("task_overdue") == "sprint"
    assert category_for_type("sprint_created") == "sprint"
    assert category_for_type("meeting") == "meeting"
    assert category_for_type("mention") == "chat"
    assert category_for_type("chat_message") == "chat"
    assert category_for_type("leave_approved") == "leave"
    assert category_for_type("escalation") == "escalation"
    assert category_for_type("something_new") == "general"


def test_dedupe_key_makes_creation_idempotent(new_user):
    user = new_user("Dedupe User")
    db = SessionLocal()
    try:
        first = create_notification(db, user["id"], "leave_submitted", "Hello", "/leave", dedupe_key="k:1")
        again = create_notification(db, user["id"], "leave_submitted", "Hello", "/leave", dedupe_key="k:1")
        assert first is not None and again is None
        assert first.category == "leave"
        # Same key for a different user is a different notification.
        other = new_user("Dedupe Other")
        assert create_notification(db, other["id"], "leave_submitted", "Hi", dedupe_key="k:1") is not None
        count = db.query(Notification).filter(Notification.user_id == user["id"], Notification.dedupe_key == "k:1").count()
        assert count == 1
    finally:
        db.close()


def test_uncommitted_notification_rolls_back_with_its_transaction(new_user):
    user = new_user("Rollback User")
    db = SessionLocal()
    try:
        create_notification(db, user["id"], "leave_submitted", "Will vanish", commit=False)
        db.rollback()
        assert db.query(Notification).filter(Notification.user_id == user["id"]).count() == 0
    finally:
        db.close()


def test_filters_unread_counts_and_mark_all_read(client, new_user):
    user = new_user("Feed User")
    db = SessionLocal()
    try:
        create_notification(db, user["id"], "task_assigned", "Task A", "/sprints")
        create_notification(db, user["id"], "leave_approved", "Leave ok", "/leave", entity_type="leave_request", entity_id=7)
        create_notification(db, user["id"], "chat_message", "Hi", "/chat")
    finally:
        db.close()
    h = user["headers"]

    counts = client.get(f"{NOTIF}/unread-count", headers=h).json()
    assert counts["total"] == 3
    assert counts["by_category"] == {"sprint": 1, "leave": 1, "chat": 1}

    leave_only = client.get(f"{NOTIF}/me", headers=h, params={"category": "leave"}).json()
    assert [n["message"] for n in leave_only] == ["Leave ok"]
    assert leave_only[0]["entity_type"] == "leave_request" and leave_only[0]["entity_id"] == 7
    assert client.get(f"{NOTIF}/me", headers=h, params={"category": "bogus"}).status_code == 422

    # Mark only one category read, then everything.
    assert client.post(f"{NOTIF}/read-all", headers=h, params={"category": "sprint"}).json()["updated"] == 1
    assert client.get(f"{NOTIF}/unread-count", headers=h).json()["total"] == 2
    assert client.post(f"{NOTIF}/read-all", headers=h).json()["updated"] == 2
    assert client.get(f"{NOTIF}/me", headers=h, params={"unread_only": True}).json() == []

    # Paging with before_id.
    page = client.get(f"{NOTIF}/me", headers=h, params={"limit": 2}).json()
    assert len(page) == 2
    rest = client.get(f"{NOTIF}/me", headers=h, params={"before_id": page[-1]["id"]}).json()
    assert len(rest) == 1


def test_users_cannot_read_or_mark_others_notifications(client, new_user):
    alice = new_user("Alice")
    bob = new_user("Bob")
    db = SessionLocal()
    try:
        note = create_notification(db, alice["id"], "task_assigned", "Private", "/sprints")
        note_id = note.id
    finally:
        db.close()
    assert client.post(f"{NOTIF}/{note_id}/read", headers=bob["headers"]).status_code == 404
    assert all(n["id"] != note_id for n in client.get(f"{NOTIF}/me", headers=bob["headers"]).json())


# ------------------------------------------------------------------ escalations

def _age_leave_request(request_id, hours):
    db = SessionLocal()
    try:
        req = db.get(LeaveRequest, request_id)
        req.created_at = datetime.now(timezone.utc) - timedelta(hours=hours)
        db.commit()
    finally:
        db.close()


def _escalations_for(request_id):
    db = SessionLocal()
    try:
        return db.query(Escalation).filter(
            Escalation.entity_type == "leave_request", Escalation.entity_id == request_id,
        ).all()
    finally:
        db.close()


def _escalation_notifications(user_id, request_id):
    db = SessionLocal()
    try:
        return db.query(Notification).filter(
            Notification.user_id == user_id, Notification.type == "escalation",
            Notification.entity_type == "leave_request", Notification.entity_id == request_id,
        ).count()
    finally:
        db.close()


def _sweep():
    db = SessionLocal()
    try:
        result = escalation_service.run_sweep(db)
        db.commit()
        return result
    finally:
        db.close()


def test_stale_leave_request_escalates_once_and_resolves(client, new_user):
    admin = new_user("Escalation Admin")
    hr = _onboard(client, admin["headers"], role="hr_manager")
    emp = _onboard(client, admin["headers"])
    req = client.post(REQUESTS, headers=emp["headers"], json={
        "leave_type": "annual", "start_date": "2027-03-01", "end_date": "2027-03-02", "reason": "Trip",
    }).json()

    # Fresh request: below the threshold, nothing escalates.
    _sweep()
    assert _escalations_for(req["id"]) == []

    _age_leave_request(req["id"], settings.LEAVE_PENDING_ESCALATION_HOURS + 1)
    _sweep()
    _sweep()  # re-running is a no-op
    escalations = _escalations_for(req["id"])
    assert len(escalations) == 1
    assert escalations[0].status == "open"
    assert escalations[0].rule == "leave_pending_overdue"
    assert escalations[0].recipient_count >= 2  # at least this admin + this HR manager
    assert _escalation_notifications(admin["id"], req["id"]) == 1
    assert _escalation_notifications(hr["user_id"], req["id"]) == 1
    assert _escalation_notifications(emp["user_id"], req["id"]) == 0  # requester isn't an approver

    # Admin/HR can list escalations; employees can't; only admin can force a run.
    listed = client.get("/api/v1/escalations", headers=hr["headers"], params={"status": "open"}).json()
    assert any(e["entity_id"] == req["id"] for e in listed)
    assert client.get("/api/v1/escalations", headers=emp["headers"]).status_code == 403
    assert client.post("/api/v1/escalations/run", headers=hr["headers"]).status_code == 403

    # Deciding the request resolves its escalation immediately.
    assert client.post(f"{REQUESTS}/{req['id']}/approve", headers=hr["headers"], json={}).status_code == 200
    escalations = _escalations_for(req["id"])
    assert escalations[0].status == "resolved" and escalations[0].resolved_at is not None
    _sweep()
    assert len(_escalations_for(req["id"])) == 1
    assert _escalation_notifications(admin["id"], req["id"]) == 1


def test_forced_sweep_endpoint_runs_and_is_throttled_otherwise(client, new_user):
    admin = new_user("Sweep Admin")
    r = client.post("/api/v1/escalations/run", headers=admin["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] is False
    assert set(r.json()["by_rule"]) == {"leave_pending_overdue", "action_items_unreviewed"}

    # The unforced path skips: it ran moments ago (throttle lives in the DB, not memory).
    db = SessionLocal()
    try:
        assert escalation_service.run_sweep_now(db) is None
    finally:
        db.close()


def test_sweep_never_breaks_notification_polling(client, new_user, monkeypatch):
    user = new_user("Polling User")
    monkeypatch.setattr(settings, "ESCALATION_AUTO_SWEEP", True)
    monkeypatch.setattr(settings, "ESCALATION_SWEEP_INTERVAL_SECONDS", 0)

    def broken(*args, **kwargs):
        raise RuntimeError("sweep exploded")

    monkeypatch.setattr(escalation_service, "run_sweep", broken)
    r = client.get(f"{NOTIF}/me", headers=user["headers"])
    assert r.status_code == 200


def test_unreviewed_action_items_escalate_to_manager_and_lead(client, new_user):
    """Rule 2: a project meeting whose AI-proposed action items sit
    unreviewed escalates to that project's Manager and Team Lead (the 4.2
    reviewers) — and resolves once nothing is left to review."""
    from models.meeting import Meeting
    from models.meeting_action_item import MeetingActionItem

    admin = new_user("Escalation Admin")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"],
                          json={"name": f"Project {_email('esc')}"}).json()
    manager = _onboard(client, admin["headers"], role="manager")
    assert client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"],
                       json={"manager_user_id": manager["user_id"]}).status_code == 200
    roles = client.get("/api/v1/auth/roles", headers=admin["headers"]).json()
    lead_email = _email("lead")
    r = client.post(f"{EMP_BASE}/employees", headers=admin["headers"], json={
        "full_name": "Escalation Lead", "email": lead_email, "role_id": next(x["id"] for x in roles if x["name"] == "employee"),
        "job_title": "Lead", "project_id": project["id"], "hire_date": "2026-01-01",
    })
    lead_employee_id = r.json()["employee"]["id"]
    lead_user_id = r.json()["employee"]["user"]["id"]
    complete_first_login(client, lead_email, r.json()["temporary_password"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"],
                json={"employee_id": lead_employee_id})

    db = SessionLocal()
    try:
        meeting = Meeting(created_by=admin["id"], title="Escalation sync", project_id=project["id"], status="completed")
        db.add(meeting)
        db.flush()
        item = MeetingActionItem(meeting_id=meeting.id, description="Write the spec", assignment_method="unassigned",
                                 status="pending", review_status="proposed", source="ai")
        db.add(item)
        db.flush()
        item.created_at = datetime.now(timezone.utc) - timedelta(hours=settings.ACTION_ITEM_REVIEW_ESCALATION_HOURS + 1)
        db.commit()
        meeting_id, item_id = meeting.id, item.id
    finally:
        db.close()

    _sweep()
    db = SessionLocal()
    try:
        esc = db.query(Escalation).filter(Escalation.entity_type == "meeting", Escalation.entity_id == meeting_id).one()
        assert esc.status == "open" and esc.recipient_count == 2
        notified = {
            n.user_id for n in db.query(Notification).filter(
                Notification.type == "escalation", Notification.entity_type == "meeting", Notification.entity_id == meeting_id,
            )
        }
        assert notified == {manager["user_id"], lead_user_id}
    finally:
        db.close()

    r = client.post(f"/api/v1/meetings/{meeting_id}/action-items/{item_id}/reject", headers=manager["headers"],
                    json={"rejection_reason": "Not agreed in the meeting."})
    assert r.status_code == 200, r.text
    _sweep()
    db = SessionLocal()
    try:
        esc = db.query(Escalation).filter(Escalation.entity_type == "meeting", Escalation.entity_id == meeting_id).one()
        assert esc.status == "resolved"
    finally:
        db.close()
