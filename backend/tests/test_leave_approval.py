"""Phase 4.3 — leave approval workflow: submission, validation, overlap
prevention, cancellation, approver RBAC, attendance + notification +
audit integration."""
from concurrent.futures import ThreadPoolExecutor

from config.database import SessionLocal
from models.audit_log import AuditLog
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
ATT_BASE = "/api/v1/attendance"
LEAVE = "/api/v1/leave"
REQUESTS = f"{LEAVE}/requests"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _onboard(client, admin_headers, email, role="employee", full_name="Leave Tester", project_id=None):
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": full_name, "email": email, "role_id": _role_id(client, admin_headers, role),
        "job_title": "Engineer", "project_id": project_id, "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    headers = complete_first_login(client, email, body["temporary_password"])
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return {"employee_id": body["employee"]["id"], "user_id": me["id"], "headers": headers, "email": email}


def _email(tag):
    import uuid
    return f"pytest_{tag}_{uuid.uuid4().hex[:8]}@example.com"


def _submit(client, headers, start="2026-12-07", end="2026-12-09", leave_type="annual", reason="Family trip"):
    return client.post(REQUESTS, headers=headers, json={
        "leave_type": leave_type, "start_date": start, "end_date": end, "reason": reason,
    })


def _audit_actions(entity_id):
    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "leave_request", AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.id)
            .all()
        )
        return [(r.action, r.actor_user_id, r.before, r.after) for r in rows]
    finally:
        db.close()


def test_leave_types_listed(client, new_user):
    admin = new_user("Leave Admin")
    r = client.get(f"{LEAVE}/types", headers=admin["headers"])
    assert r.status_code == 200
    assert set(r.json()["leave_types"]) == {"annual", "sick", "casual", "unpaid", "other"}


def test_submit_validates_dates_type_reason_and_working_days(client, new_user):
    admin = new_user("Leave Admin")
    emp = _onboard(client, admin["headers"], _email("lv"))

    assert _submit(client, emp["headers"], start="2026-12-10", end="2026-12-09").status_code == 422
    assert _submit(client, emp["headers"], leave_type="sabbatical").status_code == 422
    assert _submit(client, emp["headers"], reason="  ").status_code == 422
    # 2026-12-12/13 is a Saturday/Sunday — nothing to take off.
    r = _submit(client, emp["headers"], start="2026-12-12", end="2026-12-13")
    assert r.status_code == 400 and "working days" in r.json()["detail"]
    r = _submit(client, emp["headers"], start="2026-01-01", end="2027-03-01")
    assert r.status_code == 400

    r = _submit(client, emp["headers"], start="2026-12-07", end="2026-12-13")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["working_days"] == 5
    assert body["employee"]["id"] == emp["employee_id"]


def test_overlapping_and_duplicate_requests_rejected(client, new_user):
    admin = new_user("Leave Admin")
    emp = _onboard(client, admin["headers"], _email("lv"))

    first = _submit(client, emp["headers"], start="2026-12-14", end="2026-12-16")
    assert first.status_code == 201
    assert _submit(client, emp["headers"], start="2026-12-14", end="2026-12-16").status_code == 409  # duplicate
    assert _submit(client, emp["headers"], start="2026-12-16", end="2026-12-18").status_code == 409  # overlap
    # Adjacent (no shared day) is fine.
    assert _submit(client, emp["headers"], start="2026-12-17", end="2026-12-17").status_code == 201

    # A cancelled request no longer blocks its dates.
    r = client.post(f"{REQUESTS}/{first.json()['id']}/cancel", headers=emp["headers"])
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert _submit(client, emp["headers"], start="2026-12-14", end="2026-12-15").status_code == 201


def test_concurrent_overlapping_submissions_only_one_wins(client, new_user):
    admin = new_user("Leave Admin")
    emp = _onboard(client, admin["headers"], _email("lv"))

    def submit(_):
        return _submit(client, emp["headers"], start="2026-11-23", end="2026-11-25").status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(submit, range(4)))
    assert codes.count(201) == 1, codes
    assert codes.count(409) == 3, codes


def test_cancel_rules(client, new_user):
    admin = new_user("Leave Admin")
    emp = _onboard(client, admin["headers"], _email("lv"))
    other = _onboard(client, admin["headers"], _email("lv"))
    req = _submit(client, emp["headers"], start="2026-12-21", end="2026-12-22").json()

    # Someone else's request looks like it doesn't exist.
    assert client.post(f"{REQUESTS}/{req['id']}/cancel", headers=other["headers"]).status_code == 404
    assert client.post(f"{REQUESTS}/{req['id']}/cancel", headers=emp["headers"]).status_code == 200
    assert client.post(f"{REQUESTS}/{req['id']}/cancel", headers=emp["headers"]).status_code == 409

    approved = _submit(client, emp["headers"], start="2026-12-28", end="2026-12-28").json()
    assert client.post(f"{REQUESTS}/{approved['id']}/approve", headers=admin["headers"], json={}).status_code == 200
    assert client.post(f"{REQUESTS}/{approved['id']}/cancel", headers=emp["headers"]).status_code == 409


def test_approval_rbac(client, new_user):
    admin = new_user("Leave Admin")
    hr = _onboard(client, admin["headers"], _email("hr"), role="hr_manager")
    manager = _onboard(client, admin["headers"], _email("mgr"), role="manager")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"Project {_email('p')}"}).json()
    emp = _onboard(client, admin["headers"], _email("lv"), project_id=project["id"])
    lead = _onboard(client, admin["headers"], _email("lead"), project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"],
                json={"employee_id": lead["employee_id"]})
    viewer = new_user("Leave Viewer", role="viewer")
    req = _submit(client, emp["headers"], start="2027-01-04", end="2027-01-05").json()

    # Managers, team leads, employees and viewers can neither list nor decide.
    for actor in (manager, lead, emp, viewer):
        assert client.get(REQUESTS, headers=actor["headers"]).status_code == 403
        assert client.post(f"{REQUESTS}/{req['id']}/approve", headers=actor["headers"], json={}).status_code == 403
        assert client.post(f"{REQUESTS}/{req['id']}/reject", headers=actor["headers"],
                           json={"reason": "No cover"}).status_code == 403

    # HR Manager can see the queue and decide.
    queue = client.get(REQUESTS, headers=hr["headers"], params={"status": "pending"})
    assert queue.status_code == 200
    assert any(item["id"] == req["id"] for item in queue.json())
    assert client.post(f"{REQUESTS}/{req['id']}/approve", headers=hr["headers"], json={}).status_code == 200

    # Nobody decides on their own request — not even HR.
    own = _submit(client, hr["headers"], start="2027-01-11", end="2027-01-11").json()
    r = client.post(f"{REQUESTS}/{own['id']}/approve", headers=hr["headers"], json={})
    assert r.status_code == 403 and "own" in r.json()["detail"]
    assert client.post(f"{REQUESTS}/{own['id']}/approve", headers=admin["headers"], json={}).status_code == 200


def test_reject_requires_reason_and_decisions_are_final(client, new_user):
    admin = new_user("Leave Admin")
    emp = _onboard(client, admin["headers"], _email("lv"))
    req = _submit(client, emp["headers"], start="2027-02-01", end="2027-02-02").json()

    assert client.post(f"{REQUESTS}/{req['id']}/reject", headers=admin["headers"], json={"reason": ""}).status_code == 422
    assert client.post(f"{REQUESTS}/{req['id']}/reject", headers=admin["headers"], json={}).status_code == 422
    r = client.post(f"{REQUESTS}/{req['id']}/reject", headers=admin["headers"], json={"reason": "Release week"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    assert r.json()["decision_note"] == "Release week"
    assert r.json()["reviewed_by"]["id"] == admin["id"]

    # Already decided — can't flip it.
    assert client.post(f"{REQUESTS}/{req['id']}/approve", headers=admin["headers"], json={}).status_code == 409
    # Rejected dates are free again.
    assert _submit(client, emp["headers"], start="2027-02-01", end="2027-02-02").status_code == 201


def test_approval_marks_attendance_notifies_and_audits(client, new_user):
    admin = new_user("Leave Admin")
    hr = _onboard(client, admin["headers"], _email("hr"), role="hr_manager")
    emp = _onboard(client, admin["headers"], _email("lv"))
    req = _submit(client, emp["headers"], start="2026-11-02", end="2026-11-04", leave_type="sick",
                  reason="Flu — doctor's note").json()

    # Submission notified the approvers (in the leave category, pointing at the request).
    hr_notes = client.get("/api/v1/notifications/me", headers=hr["headers"], params={"category": "leave"}).json()
    submitted = [n for n in hr_notes if n["entity_type"] == "leave_request" and n["entity_id"] == req["id"]]
    assert len(submitted) == 1 and submitted[0]["type"] == "leave_submitted"

    r = client.post(f"{REQUESTS}/{req['id']}/approve", headers=hr["headers"], json={"note": "Get well soon"})
    assert r.status_code == 200, r.text

    # Attendance days are on_leave, with a neutral note (not the private reason).
    records = client.get(f"{ATT_BASE}/me", headers=emp["headers"],
                         params={"start_date": "2026-11-02", "end_date": "2026-11-04"}).json()
    assert len(records) == 3 and all(rec["status"] == "on_leave" for rec in records)
    assert all("doctor" not in (rec["notes"] or "") for rec in records)

    mine = client.get("/api/v1/notifications/me", headers=emp["headers"], params={"category": "leave"}).json()
    decided = [n for n in mine if n["entity_id"] == req["id"]]
    assert len(decided) == 1 and decided[0]["type"] == "leave_approved"

    history = client.get(REQUESTS, headers=admin["headers"], params={"employee_id": emp["employee_id"]}).json()
    assert [h["status"] for h in history] == ["approved"]

    actions = _audit_actions(req["id"])
    assert [a[0] for a in actions] == ["leave_request.submitted", "leave_request.approved"]
    submitted_row, approved_row = actions
    assert submitted_row[1] == emp["user_id"]
    assert approved_row[1] == hr["user_id"]
    assert approved_row[2]["status"] == "pending" and approved_row[3]["status"] == "approved"
    # The free-text reason never reaches the audit trail.
    assert all("reason" not in (a[3] or {}) and "reason" not in (a[2] or {}) for a in actions)


def test_failed_decision_leaves_no_partial_state(client, new_user, monkeypatch):
    """If anything inside the approval transaction fails, the status,
    attendance, notification and audit row all roll back together."""
    admin = new_user("Leave Admin")
    emp = _onboard(client, admin["headers"], _email("lv"))
    req = _submit(client, emp["headers"], start="2026-11-09", end="2026-11-10").json()

    from modules.leave import service as leave_service

    def boom(*args, **kwargs):
        raise RuntimeError("notification outage")

    monkeypatch.setattr(leave_service, "create_notification", boom)
    try:
        client.post(f"{REQUESTS}/{req['id']}/approve", headers=admin["headers"], json={})
    except RuntimeError:
        pass  # TestClient re-raises unhandled server errors
    monkeypatch.undo()

    mine = client.get(f"{REQUESTS}/me", headers=emp["headers"]).json()
    assert next(m for m in mine if m["id"] == req["id"])["status"] == "pending"
    records = client.get(f"{ATT_BASE}/me", headers=emp["headers"],
                         params={"start_date": "2026-11-09", "end_date": "2026-11-10"}).json()
    assert records == []
    assert [a[0] for a in _audit_actions(req["id"])] == ["leave_request.submitted"]

    # And it can still be approved normally afterwards.
    assert client.post(f"{REQUESTS}/{req['id']}/approve", headers=admin["headers"], json={}).status_code == 200


def test_admin_without_employee_record_cannot_submit(client, new_user):
    admin = new_user("Leave Admin")
    r = _submit(client, admin["headers"])
    assert r.status_code == 404
