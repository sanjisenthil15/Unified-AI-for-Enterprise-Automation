"""Attendance module — check-in/check-out, leave, and team views."""
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
ATT_BASE = "/api/v1/attendance"
LEAVE_REQUESTS = "/api/v1/leave/requests"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _onboard(client, admin_headers, email, full_name="Test Employee", project_id=None):
    role_id = _role_id(client, admin_headers, "employee")
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": full_name, "email": email, "role_id": role_id,
        "job_title": "Engineer", "project_id": project_id, "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    temp_password = r.json()["temporary_password"]
    employee_id = r.json()["employee"]["id"]
    headers = complete_first_login(client, email, temp_password)
    return {"employee_id": employee_id, "headers": headers}


def test_check_in_then_check_out(client, new_user, unique_email):
    admin = new_user("Admin User")
    emp = _onboard(client, admin["headers"], unique_email)

    r = client.post(f"{ATT_BASE}/check-in", headers=emp["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["check_in_at"] is not None
    assert r.json()["check_out_at"] is None

    # A second check-in the same day is rejected.
    assert client.post(f"{ATT_BASE}/check-in", headers=emp["headers"]).status_code == 409

    r = client.post(f"{ATT_BASE}/check-out", headers=emp["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["check_out_at"] is not None

    # A second check-out the same day is rejected.
    assert client.post(f"{ATT_BASE}/check-out", headers=emp["headers"]).status_code == 409


def test_check_out_before_check_in_rejected(client, new_user, unique_email):
    admin = new_user("Admin User")
    emp = _onboard(client, admin["headers"], unique_email)
    assert client.post(f"{ATT_BASE}/check-out", headers=emp["headers"]).status_code == 400


def test_team_attendance_requires_team_lead_or_admin(client, new_user, unique_email):
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"Project {unique_email}",
    }).json()

    member = _onboard(client, admin["headers"], unique_email, project_id=project["id"])
    client.post(f"{ATT_BASE}/check-in", headers=member["headers"])

    # A plain team member (not the lead) cannot see the team view.
    r = client.get(f"{ATT_BASE}/team", headers=member["headers"], params={"project_id": project["id"]})
    assert r.status_code == 403

    # Admin (role override — no Employee record of their own) can.
    r = client.get(f"{ATT_BASE}/team", headers=admin["headers"], params={"project_id": project["id"]})
    assert r.status_code == 200, r.text
    assert any(e["employee"]["id"] == member["employee_id"] for e in r.json())

    # Promote the member to team lead of their own project — now they can see it too.
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"],
                json={"employee_id": member["employee_id"]})
    r = client.get(f"{ATT_BASE}/team", headers=member["headers"], params={"project_id": project["id"]})
    assert r.status_code == 200, r.text


def test_leave_marking_excluded_from_checkin_rate(client, new_user, unique_email):
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"Project {unique_email}",
    }).json()
    member = _onboard(client, admin["headers"], unique_email, project_id=project["id"])

    window = {"start_date": "2026-01-05", "end_date": "2026-01-09"}

    # Self-marking leave was retired in Phase 4.3 — it bypassed approval.
    r = client.post(f"{ATT_BASE}/leave", headers=member["headers"], json={**window, "reason": "Planned vacation"})
    assert r.status_code == 410, r.text

    # Leave now goes through approval; a pending request marks nothing yet.
    r = client.post(LEAVE_REQUESTS, headers=member["headers"], json={
        **window, "leave_type": "annual", "reason": "Planned vacation",
    })
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    detail = client.get(f"{ATT_BASE}/employee/{member['employee_id']}", headers=admin["headers"], params=window)
    assert detail.status_code == 200, detail.text
    assert detail.json()["checkin_rate"] == 0.0

    # Once HR/Admin approves it, the whole window is on_leave -> the
    # business-day denominator is fully excluded, so a manager viewing
    # this employee doesn't see them penalized for it.
    r = client.post(f"{LEAVE_REQUESTS}/{request_id}/approve", headers=admin["headers"], json={})
    assert r.status_code == 200, r.text
    detail = client.get(f"{ATT_BASE}/employee/{member['employee_id']}", headers=admin["headers"], params=window)
    assert detail.status_code == 200, detail.text
    assert all(rec["status"] == "on_leave" for rec in detail.json()["records"])
    assert len(detail.json()["records"]) == 5
    assert detail.json()["checkin_rate"] == 1.0
