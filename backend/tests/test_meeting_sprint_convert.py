"""Meeting Intelligence -> Sprints: converting an action item into an assigned task."""

from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem

EMP_BASE = "/api/v1/employee-management"
SPR_BASE = "/api/v1/sprints"
MEETINGS_BASE = "/api/v1/meetings"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _tag(unique_email, tag):
    return unique_email.replace("pytest_", f"pytest_{tag}_", 1)


def _onboard(client, admin_headers, email, full_name="Test Employee", project_id=None):
    role_id = _role_id(client, admin_headers, "employee")
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": full_name, "email": email, "role_id": role_id,
        "job_title": "Engineer", "project_id": project_id, "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    temp_password = r.json()["temporary_password"]
    employee_id = r.json()["employee"]["id"]
    user_id = r.json()["employee"]["user"]["id"]
    login = client.post("/api/v1/auth/login", json={"email": email, "password": temp_password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return {"employee_id": employee_id, "user_id": user_id, "headers": headers}


def test_convert_action_item_creates_sprint_task(client, db, new_user, unique_email):
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"Project {unique_email}",
    }).json()
    lead = _onboard(client, admin["headers"], _tag(unique_email, "lead"), "Team Lead", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"],
                json={"employee_id": lead["employee_id"]})
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    sprint = client.post(SPR_BASE, headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2026-01-05", "end_date": "2026-01-11",
    }).json()

    # Directly seed a meeting + action item (bypassing the upload/AI pipeline,
    # same pattern as test_meeting_api.py's _fake_success), owned by the lead
    # and linked to the project.
    meeting = Meeting(created_by=lead["user_id"], title="Sprint planning", project_id=project["id"], status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(
        meeting_id=meeting.id, description="Complete the frontend button module",
        assignment_method="unassigned", status="pending", source="ai",
    )
    db.add(item)
    db.commit()
    meeting_id, item_id = meeting.id, item.id

    r = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/convert",
        headers=lead["headers"],
        json={"sprint_id": sprint["id"], "assignee_id": member["employee_id"], "due_date": "2026-01-10"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["converted_sprint_task_id"] is not None
    assert body["assigned_to_employee_id"] == member["employee_id"]

    tasks = client.get(f"{SPR_BASE}/{sprint['id']}/tasks", headers=lead["headers"]).json()
    task = next(t for t in tasks if t["id"] == body["converted_sprint_task_id"])
    assert task["title"] == "Complete the frontend button module"
    assert task["assignee"]["id"] == member["employee_id"]

    # Re-converting the same item is rejected.
    r = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/convert",
        headers=lead["headers"],
        json={"sprint_id": sprint["id"], "assignee_id": member["employee_id"]},
    )
    assert r.status_code == 409

    db.query(MeetingActionItem).filter(MeetingActionItem.id == item_id).delete()
    db.query(Meeting).filter(Meeting.id == meeting_id).delete()
    db.commit()


def test_convert_requires_meeting_linked_to_a_project(client, db, new_user, unique_email):
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"Project {unique_email}",
    }).json()
    lead = _onboard(client, admin["headers"], _tag(unique_email, "lead"), "Team Lead", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"],
                json={"employee_id": lead["employee_id"]})
    sprint = client.post(SPR_BASE, headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2026-01-05", "end_date": "2026-01-11",
    }).json()

    meeting = Meeting(created_by=lead["user_id"], title="Unlinked meeting", status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(meeting_id=meeting.id, description="Do something", assignment_method="unassigned", status="pending", source="ai")
    db.add(item)
    db.commit()
    meeting_id, item_id = meeting.id, item.id

    r = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/convert",
        headers=lead["headers"],
        json={"sprint_id": sprint["id"], "assignee_id": lead["employee_id"]},
    )
    assert r.status_code == 400

    db.query(MeetingActionItem).filter(MeetingActionItem.id == item_id).delete()
    db.query(Meeting).filter(Meeting.id == meeting_id).delete()
    db.commit()
