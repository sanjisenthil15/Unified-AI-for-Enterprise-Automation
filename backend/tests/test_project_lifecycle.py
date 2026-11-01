"""
test_project_lifecycle.py

Comprehensive test suite for EnterpriseAI Phase 4.1: Project Lifecycle.
Tests:
1. Creation defaults (status="planning") & start_date/deadline validation.
2. Lifecycle state transitions & timestamps (cancelled_at, completed_at, archived_at).
3. Prohibition on reopening completed/cancelled projects & un-archiving.
4. Completion validation (blocked by open sprints or unresolved tasks).
5. Operational guard on non-active projects (sprint/task mutations blocked).
6. Action-item conversion blocked on non-active projects.
7. Preservation of read access across all lifecycle states.
8. Role-scoped visibility & PII privacy.
9. Project deletion safety (restricted if associations exist).
"""
from datetime import date, timedelta
import pytest

from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.project import Project
from models.sprint import Sprint
from models.sprint_task import SprintTask
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
SPR_BASE = "/api/v1/sprints"
MEETINGS_BASE = "/api/v1/meetings"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _tag(unique_email, tag):
    return unique_email.replace("pytest_", f"pytest_{tag}_", 1)


def _onboard_user(client, admin_headers, email, role_name, full_name="Test User", project_id=None):
    role_id = _role_id(client, admin_headers, role_name)
    payload = {
        "full_name": full_name,
        "email": email,
        "role_id": role_id,
        "job_title": "Engineer" if role_name == "employee" else "Lead" if role_name == "team_lead" else "Staff",
        "hire_date": "2026-01-01",
    }
    if project_id is not None:
        payload["project_id"] = project_id
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    temp_password = r.json()["temporary_password"]
    employee_id = r.json()["employee"]["id"]
    user_id = r.json()["employee"]["user"]["id"]
    headers = complete_first_login(client, email, temp_password)
    return {"employee_id": employee_id, "user_id": user_id, "headers": headers}


def test_project_creation_and_defaults(client, new_user, unique_email):
    admin = new_user("Admin User")

    # 1. Default creation starts in 'planning'
    r = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_Plan_{unique_email}",
        "description": "Planning description",
        "start_date": "2026-03-01",
        "deadline": "2026-06-01",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "planning"
    assert data["start_date"] == "2026-03-01"
    assert data["deadline"] == "2026-06-01"
    assert data["completed_at"] is None
    assert data["cancelled_at"] is None
    assert data["archived_at"] is None

    # 2. Invalid dates: deadline before start_date
    r_bad = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_BadDates_{unique_email}",
        "start_date": "2026-06-01",
        "deadline": "2026-03-01",
    })
    assert r_bad.status_code == 400


def test_lifecycle_cancellation_timestamp(client, new_user, unique_email):
    """Verifies active -> cancelled sets cancelled_at, leaves completed_at NULL, and archive preserves cancelled_at."""
    admin = new_user("Admin User")
    r = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_Cancel_{unique_email}", "status": "active"
    })
    assert r.status_code == 201
    proj_id = r.json()["id"]

    # Transition active -> cancelled
    r_cancel = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=admin["headers"], json={
        "status": "cancelled"
    })
    assert r_cancel.status_code == 200, r_cancel.text
    data_cancel = r_cancel.json()
    assert data_cancel["status"] == "cancelled"
    assert data_cancel["cancelled_at"] is not None
    assert data_cancel["completed_at"] is None

    # Transition cancelled -> archived (preserves cancelled_at)
    r_arch = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=admin["headers"], json={
        "status": "archived"
    })
    assert r_arch.status_code == 200, r_arch.text
    data_arch = r_arch.json()
    assert data_arch["status"] == "archived"
    assert data_arch["archived_at"] is not None
    assert data_arch["cancelled_at"] == data_cancel["cancelled_at"]
    assert data_arch["completed_at"] is None


def test_lifecycle_completion_validation_and_timestamp(client, db, new_user, unique_email):
    """Verifies completion requires 0 uncompleted sprints and 0 unresolved tasks, setting completed_at."""
    admin = new_user("Admin User")
    r = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_Complete_{unique_email}", "status": "active"
    })
    proj_id = r.json()["id"]
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgro"), "manager", "Mgr O")
    client.post(f"{EMP_BASE}/projects/{proj_id}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    # Add active sprint and task
    sprint = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": proj_id, "name": "Sprint 1", "start_date": "2026-01-01", "end_date": "2026-01-07"
    }).json()

    task = client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=mgr["headers"], json={
        "title": "Open Task"
    }).json()

    # Attempt to complete project -> blocked because sprint and task are not completed
    r_fail = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=mgr["headers"], json={"status": "completed"})
    assert r_fail.status_code == 400
    assert "sprint(s) are not completed" in r_fail.json()["detail"]

    # Mark task as done
    client.patch(f"{SPR_BASE}/tasks/{task['id']}", headers=mgr["headers"], json={"status": "done"})

    # Still blocked because sprint is planned/active, not completed
    r_fail2 = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=mgr["headers"], json={"status": "completed"})
    assert r_fail2.status_code == 400
    assert "sprint(s) are not completed" in r_fail2.json()["detail"]

    # Complete the sprint
    client.patch(f"{SPR_BASE}/{sprint['id']}", headers=mgr["headers"], json={"status": "completed"})

    # Now completion succeeds
    r_comp = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=mgr["headers"], json={"status": "completed"})
    assert r_comp.status_code == 200, r_comp.text
    data_comp = r_comp.json()
    assert data_comp["status"] == "completed"
    assert data_comp["completed_at"] is not None
    assert data_comp["cancelled_at"] is None

    # Transition completed -> archived preserves completed_at
    r_arch = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=mgr["headers"], json={"status": "archived"})
    assert r_arch.status_code == 200
    assert r_arch.json()["completed_at"] == data_comp["completed_at"]
    assert r_arch.json()["archived_at"] is not None


def test_reopening_and_unarchiving_prohibited(client, new_user, unique_email):
    """Verifies that completed/cancelled projects cannot reopen and archived cannot transition."""
    admin = new_user("Admin User")
    r = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_NoReopen_{unique_email}", "status": "active"
    })
    proj_id = r.json()["id"]

    # Cancel project
    client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=admin["headers"], json={"status": "cancelled"})

    # Attempt to reopen cancelled -> active (blocked!)
    r_reopen = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=admin["headers"], json={"status": "active"})
    assert r_reopen.status_code == 400
    assert "Reopening completed or cancelled projects is not allowed" in r_reopen.json()["detail"]

    # Archive project
    client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=admin["headers"], json={"status": "archived"})

    # Attempt un-archiving archived -> active (blocked!)
    r_unarch = client.patch(f"{EMP_BASE}/projects/{proj_id}/status", headers=admin["headers"], json={"status": "active"})
    assert r_unarch.status_code == 400


def test_sprint_and_task_mutations_blocked_on_non_active_projects(client, db, new_user, unique_email):
    """Verifies that sprints and tasks cannot be created or modified on non-active projects."""
    admin = new_user("Admin User")
    # Project in planning
    proj_plan = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_BlockedPlan_{unique_email}", "status": "planning"
    }).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrb"), "manager", "Mgr B")
    client.post(f"{EMP_BASE}/projects/{proj_plan['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    # create_sprint blocked
    r_spr = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": proj_plan["id"], "name": "Sprint B", "start_date": "2026-01-01", "end_date": "2026-01-07"
    })
    assert r_spr.status_code == 400
    assert "Project must be 'active'" in r_spr.json()["detail"]

    # Activate project, create sprint and task, then put on hold
    client.patch(f"{EMP_BASE}/projects/{proj_plan['id']}/status", headers=mgr["headers"], json={"status": "active"})
    sprint = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": proj_plan["id"], "name": "Sprint Active", "start_date": "2026-01-01", "end_date": "2026-01-07"
    }).json()
    task = client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=mgr["headers"], json={"title": "Task Active"}).json()

    # Transition to on_hold
    client.patch(f"{EMP_BASE}/projects/{proj_plan['id']}/status", headers=mgr["headers"], json={"status": "on_hold"})

    # update_sprint blocked on on_hold
    r_up_spr = client.patch(f"{SPR_BASE}/{sprint['id']}", headers=mgr["headers"], json={"name": "Sprint Renamed"})
    assert r_up_spr.status_code == 400
    assert "Project must be 'active'" in r_up_spr.json()["detail"]

    # create_task blocked on on_hold
    r_cr_tsk = client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=mgr["headers"], json={"title": "New Task"})
    assert r_cr_tsk.status_code == 400
    assert "Project must be 'active'" in r_cr_tsk.json()["detail"]

    # update_task blocked on on_hold
    r_up_tsk = client.patch(f"{SPR_BASE}/tasks/{task['id']}", headers=mgr["headers"], json={"title": "Task Renamed"})
    assert r_up_tsk.status_code == 400
    assert "Project must be 'active'" in r_up_tsk.json()["detail"]

    # Historical read access remains 200 OK!
    r_read_sprints = client.get(f"{SPR_BASE}?project_id={proj_plan['id']}", headers=mgr["headers"])
    assert r_read_sprints.status_code == 200
    assert len(r_read_sprints.json()) == 1

    r_read_tasks = client.get(f"{SPR_BASE}/{sprint['id']}/tasks", headers=mgr["headers"])
    assert r_read_tasks.status_code == 200
    assert len(r_read_tasks.json()) == 1


def test_action_item_conversion_blocked_on_non_active_projects(client, db, new_user, unique_email):
    """Verifies that converting action items to tasks requires active project."""
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"P_Conv_{unique_email}", "status": "active"
    }).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrc"), "manager", "Mgr C")
    member = _onboard_user(client, admin["headers"], _tag(unique_email, "memc"), "employee", "Mem C", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    sprint = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": project["id"], "name": "Sprint C", "start_date": "2026-04-01", "end_date": "2026-04-07"
    }).json()

    meeting = Meeting(created_by=mgr["user_id"], title="Review", project_id=project["id"], status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(
        meeting_id=meeting.id, description="AI Task", assignment_method="unassigned",
        status="pending", review_status="proposed", source="ai",
    )
    db.add(item)
    db.commit()

    # Confirm action item
    client.post(f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/confirm", headers=mgr["headers"], json={
        "assignee_id": member["employee_id"], "due_date": "2026-04-05"
    })

    # Transition project to on_hold
    client.patch(f"{EMP_BASE}/projects/{project['id']}/status", headers=mgr["headers"], json={"status": "on_hold"})

    # Conversion attempt blocked because project is on_hold!
    r_conv = client.post(f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/convert", headers=mgr["headers"], json={
        "sprint_id": sprint["id"]
    })
    assert r_conv.status_code == 400
    assert "Project must be 'active'" in r_conv.json()["detail"]


def test_role_scoped_project_visibility_and_privacy(client, new_user, unique_email):
    """Verifies that employees, team leads, and managers only see their assigned projects and member data."""
    admin = new_user("Admin User")
    proj_a = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"P_A_{unique_email}", "status": "active"}).json()
    proj_b = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"P_B_{unique_email}", "status": "active"}).json()

    mgr_a = _onboard_user(client, admin["headers"], _tag(unique_email, "mgra"), "manager", "Mgr A")
    lead_a = _onboard_user(client, admin["headers"], _tag(unique_email, "leada"), "employee", "Lead A", project_id=proj_a["id"])
    emp_a = _onboard_user(client, admin["headers"], _tag(unique_email, "empa"), "employee", "Emp A", project_id=proj_a["id"])

    client.post(f"{EMP_BASE}/projects/{proj_a['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr_a["user_id"]})
    client.post(f"{EMP_BASE}/projects/{proj_a['id']}/team-lead", headers=admin["headers"], json={"employee_id": lead_a["employee_id"]})

    # 1. Admin sees both projects
    listing_admin = client.get(f"{EMP_BASE}/projects", headers=admin["headers"]).json()
    assert any(p["id"] == proj_a["id"] for p in listing_admin)
    assert any(p["id"] == proj_b["id"] for p in listing_admin)

    # 2. Manager A sees only proj_a
    listing_mgr_a = client.get(f"{EMP_BASE}/projects", headers=mgr_a["headers"]).json()
    assert any(p["id"] == proj_a["id"] for p in listing_mgr_a)
    assert not any(p["id"] == proj_b["id"] for p in listing_mgr_a)

    # Manager A can view proj_a detail, but receives 403 on proj_b
    assert client.get(f"{EMP_BASE}/projects/{proj_a['id']}", headers=mgr_a["headers"]).status_code == 200
    assert client.get(f"{EMP_BASE}/projects/{proj_b['id']}", headers=mgr_a["headers"]).status_code == 403

    # 3. Employee A sees only proj_a
    listing_emp_a = client.get(f"{EMP_BASE}/projects", headers=emp_a["headers"]).json()
    assert any(p["id"] == proj_a["id"] for p in listing_emp_a)
    assert not any(p["id"] == proj_b["id"] for p in listing_emp_a)

    # Employee A cannot modify metadata or status on proj_a (read-only!)
    r_patch = client.patch(f"{EMP_BASE}/projects/{proj_a['id']}", headers=emp_a["headers"], json={"name": "Hacked"})
    assert r_patch.status_code == 403
    r_stat = client.patch(f"{EMP_BASE}/projects/{proj_a['id']}/status", headers=emp_a["headers"], json={"status": "cancelled"})
    assert r_stat.status_code == 403

    # 4. Team Lead A cannot modify metadata or status (read-only!)
    r_tl_patch = client.patch(f"{EMP_BASE}/projects/{proj_a['id']}", headers=lead_a["headers"], json={"name": "Hacked"})
    assert r_tl_patch.status_code == 403

    # 5. Assigned Manager A CAN modify metadata and status on proj_a
    r_mgr_patch = client.patch(f"{EMP_BASE}/projects/{proj_a['id']}", headers=mgr_a["headers"], json={"description": "Updated by Mgr A"})
    assert r_mgr_patch.status_code == 200, r_mgr_patch.text
    assert r_mgr_patch.json()["description"] == "Updated by Mgr A"


def test_safe_project_deletion_and_archival(client, new_user, unique_email):
    """Verifies that projects with sprints/employees cannot be hard-deleted, but empty projects can."""
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"P_Del_{unique_email}", "status": "active"}).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrd"), "manager", "Mgr D")
    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    # Add sprint
    client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": project["id"], "name": "Sprint D", "start_date": "2026-05-01", "end_date": "2026-05-07"
    })

    # Deletion blocked because sprint exists
    r_del = client.delete(f"{EMP_BASE}/projects/{project['id']}", headers=admin["headers"])
    assert r_del.status_code == 400
    assert "associated sprints, meetings, or employees" in r_del.json()["detail"]

    # Create empty clean project
    clean_proj = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"P_Clean_{unique_email}", "status": "planning"}).json()

    # Manager cannot delete
    assert client.delete(f"{EMP_BASE}/projects/{clean_proj['id']}", headers=mgr["headers"]).status_code == 403

    # Admin can hard delete clean project
    r_del_ok = client.delete(f"{EMP_BASE}/projects/{clean_proj['id']}", headers=admin["headers"])
    assert r_del_ok.status_code == 200, r_del_ok.text

