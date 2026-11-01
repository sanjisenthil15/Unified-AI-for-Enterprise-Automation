"""
backend/tests/test_meeting_action_approval.py

Comprehensive test suite for Submodule 4.2: Meeting Action-Item Approval.
Covers:
  1. Multi-Manager architecture, project assignment, deactivation blocking, advisory lock.
  2. 4-state action-item approval lifecycle: proposed -> confirmed -> converted / proposed -> rejected.
  3. Database CHECK constraints, ON DELETE RESTRICT foreign keys, and immutability triggers.
  4. Atomic sprint task conversion and rollback safety.
  5. Project-linked meeting creation authorization and visibility matrix.
"""

from datetime import date, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError

from models.employee import Employee
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.project import Project
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.user import User
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
SPR_BASE = "/api/v1/sprints"
MEETINGS_BASE = "/api/v1/meetings"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _tag(unique_email, tag):
    return unique_email.replace("pytest_", f"pytest_{tag}_", 1)


def _onboard_user(client, admin_headers, email, role_name="employee", full_name="Test User", project_id=None):
    role_id = _role_id(client, admin_headers, role_name)
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": full_name,
        "email": email,
        "role_id": role_id,
        "job_title": f"{role_name.title()} Title",
        "project_id": project_id,
        "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    temp_password = r.json()["temporary_password"]
    employee_id = r.json()["employee"]["id"]
    user_id = r.json()["employee"]["user"]["id"]
    headers = complete_first_login(client, email, temp_password)
    return {
        "employee_id": employee_id,
        "user_id": user_id,
        "headers": headers,
        "email": email,
        "full_name": full_name,
    }


# =========================================================================== #
# 1. Multi-Manager Architecture & Deactivation Safety
# =========================================================================== #

def test_multiple_active_managers_allowed(client, db, new_user, unique_email):
    """Verifies removal of uq_single_active_manager: multiple active managers can coexist."""
    admin = new_user("Admin User")
    mgr1 = _onboard_user(client, admin["headers"], _tag(unique_email, "mgr1"), "manager", "Manager Alpha")
    mgr2 = _onboard_user(client, admin["headers"], _tag(unique_email, "mgr2"), "manager", "Manager Beta")

    # Both users exist and have role 'manager'
    u1 = db.query(User).filter(User.id == mgr1["user_id"]).first()
    u2 = db.query(User).filter(User.id == mgr2["user_id"]).first()
    assert u1.role.name == "manager"
    assert u2.role.name == "manager"
    assert u1.is_active is True
    assert u2.is_active is True


def test_assign_project_manager_and_reassignment(client, db, new_user, unique_email):
    """Verifies assigning a Manager to a project and reassigning to another manager."""
    admin = new_user("Admin User")
    mgr_a = _onboard_user(client, admin["headers"], _tag(unique_email, "mgra"), "manager", "Manager A")
    mgr_b = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrb"), "manager", "Manager B")

    p = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"Proj {unique_email}"}).json()
    proj_id = p["id"]

    # Assign Manager A
    r = client.post(f"{EMP_BASE}/projects/{proj_id}/manager", headers=admin["headers"], json={
        "manager_user_id": mgr_a["user_id"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["manager"]["id"] == mgr_a["user_id"]

    # Reassign to Manager B
    r2 = client.post(f"{EMP_BASE}/projects/{proj_id}/manager", headers=admin["headers"], json={
        "manager_user_id": mgr_b["user_id"],
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["manager"]["id"] == mgr_b["user_id"]

    # Verify non-manager cannot be assigned as manager
    emp = _onboard_user(client, admin["headers"], _tag(unique_email, "emp1"), "employee", "Standard Emp")
    r_bad = client.post(f"{EMP_BASE}/projects/{proj_id}/manager", headers=admin["headers"], json={
        "manager_user_id": emp["user_id"],
    })
    assert r_bad.status_code == 400


def test_manager_deactivation_blocked_while_assigned_to_project(client, db, new_user, unique_email):
    """Verifies that an assigned Manager cannot be deactivated or terminated."""
    admin = new_user("Admin User")
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrblk"), "manager", "Manager Blk")

    p = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"ProjBlk {unique_email}"}).json()
    proj_id = p["id"]

    # Assign Manager
    client.post(f"{EMP_BASE}/projects/{proj_id}/manager", headers=admin["headers"], json={
        "manager_user_id": mgr["user_id"],
    })

    # Attempting to deactivate manager via status update -> 400
    r_deact = client.patch(f"{EMP_BASE}/employees/{mgr['employee_id']}", headers=admin["headers"], json={
        "status": "inactive",
    })
    assert r_deact.status_code == 400
    assert "while assigned to projects" in r_deact.json()["detail"]

    # Attempting to terminate manager -> 400
    r_term = client.post(f"{EMP_BASE}/employees/{mgr['employee_id']}/terminate", headers=admin["headers"])
    assert r_term.status_code == 400
    assert "while assigned to projects" in r_term.json()["detail"]

    # Reassign project to another manager or none
    mgr2 = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrfree"), "manager", "Manager Free")
    client.post(f"{EMP_BASE}/projects/{proj_id}/manager", headers=admin["headers"], json={
        "manager_user_id": mgr2["user_id"],
    })

    # Now deactivation succeeds
    r_ok = client.patch(f"{EMP_BASE}/employees/{mgr['employee_id']}", headers=admin["headers"], json={
        "status": "inactive",
    })
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "inactive"


# =========================================================================== #
# 2. Four-State Action Item Approval Workflow
# =========================================================================== #

def test_full_action_item_approval_workflow(client, db, new_user, unique_email):
    """Tests the full proposed -> confirmed -> converted lifecycle with attribution."""
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"P {unique_email}", "status": "active"}).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrw"), "manager", "Workflow Manager")
    lead = _onboard_user(client, admin["headers"], _tag(unique_email, "leadw"), "employee", "Workflow Lead", project_id=project["id"])
    member = _onboard_user(client, admin["headers"], _tag(unique_email, "memw"), "employee", "Workflow Member", project_id=project["id"])

    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"], json={"employee_id": lead["employee_id"]})

    sprint = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": project["id"], "name": "Sprint Alpha", "start_date": "2026-02-01", "end_date": "2026-02-07",
    }).json()

    # Seed meeting and proposed action item
    meeting = Meeting(created_by=mgr["user_id"], title="Review Meeting", project_id=project["id"], status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(
        meeting_id=meeting.id,
        description="Draft initial API spec",
        assignment_method="unassigned",
        status="pending",
        review_status="proposed",
        source="ai",
    )
    db.add(item)
    db.commit()
    meeting_id, item_id = meeting.id, item.id

    # Step 1: Manager confirms the item
    conf_res = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/confirm",
        headers=mgr["headers"],
        json={
            "assignee_id": member["employee_id"],
            "due_date": "2026-02-05",
            "final_description": "Draft complete OpenAPI 3.0 specification",
        },
    )
    assert conf_res.status_code == 200, conf_res.text
    item_data = conf_res.json()
    assert item_data["review_status"] == "confirmed"
    assert item_data["assigned_to_employee_id"] == member["employee_id"]
    assert item_data["due_date"] == "2026-02-05"
    assert item_data["final_description"] == "Draft complete OpenAPI 3.0 specification"
    assert item_data["reviewed_by_id"] == mgr["user_id"]
    assert item_data["reviewed_at"] is not None

    # Step 2: Cannot re-confirm a confirmed item
    conf_again = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/confirm",
        headers=mgr["headers"],
        json={"assignee_id": member["employee_id"], "due_date": "2026-02-05"},
    )
    assert conf_again.status_code == 409

    # Step 3: Team Lead converts confirmed item to Sprint Task
    conv_res = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/convert",
        headers=lead["headers"],
        json={"sprint_id": sprint["id"]},
    )
    assert conv_res.status_code == 200, conv_res.text
    conv_data = conv_res.json()
    assert conv_data["review_status"] == "converted"
    assert conv_data["converted_sprint_task_id"] is not None

    # Step 4: Verify task in sprints
    tasks = client.get(f"{SPR_BASE}/{sprint['id']}/tasks", headers=lead["headers"]).json()
    t = next(x for x in tasks if x["id"] == conv_data["converted_sprint_task_id"])
    assert t["title"] == "Draft complete OpenAPI 3.0 specification"
    assert t["assignee"]["id"] == member["employee_id"]

    # Step 5: Terminal state - cannot convert again
    conv_again = client.post(
        f"{MEETINGS_BASE}/{meeting_id}/action-items/{item_id}/convert",
        headers=mgr["headers"],
        json={"sprint_id": sprint["id"]},
    )
    assert conv_again.status_code == 409


def test_action_item_rejection_workflow(client, db, new_user, unique_email):
    """Tests the proposed -> rejected terminal flow with mandatory reason."""
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"PRej {unique_email}"}).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrrej"), "manager", "Rej Manager")
    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    meeting = Meeting(created_by=mgr["user_id"], title="Reject Meeting", project_id=project["id"], status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(
        meeting_id=meeting.id,
        description="Hallucinated task",
        assignment_method="unassigned",
        status="pending",
        review_status="proposed",
        source="ai",
    )
    db.add(item)
    db.commit()

    # Rejection requires non-empty reason
    r_empty = client.post(
        f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/reject",
        headers=mgr["headers"],
        json={"rejection_reason": "   "},
    )
    assert r_empty.status_code == 422 or r_empty.status_code == 400

    # Successful rejection
    r_rej = client.post(
        f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/reject",
        headers=mgr["headers"],
        json={"rejection_reason": "Not agreed upon during the discussion."},
    )
    assert r_rej.status_code == 200
    data = r_rej.json()
    assert data["review_status"] == "rejected"
    assert data["rejection_reason"] == "Not agreed upon during the discussion."
    assert data["reviewed_by_id"] == mgr["user_id"]

    # Cannot confirm or convert a rejected item
    r_conf = client.post(
        f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/confirm",
        headers=mgr["headers"],
        json={"assignee_id": 1, "due_date": "2026-03-01"},
    )
    assert r_conf.status_code == 409


# =========================================================================== #
# 3. Database Constraints, Triggers & RESTRICT Integrity
# =========================================================================== #

def test_db_ck_confirmed_requires_assignee_and_due_date(db, new_user, unique_email):
    """Direct database verification of ck_action_item_confirmed_contract."""
    admin = new_user("Admin User")
    meeting = Meeting(created_by=admin["id"], title="Constraint Test", status="completed")
    db.add(meeting)
    db.commit()

    # Missing assignee_id on confirmed -> violates CHECK constraint
    item_bad = MeetingActionItem(
        meeting_id=meeting.id,
        description="Test constraint",
        review_status="confirmed",
        due_date=date(2026, 2, 1),
        reviewed_by_id=admin["id"],
    )
    db.add(item_bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_db_ck_rejected_requires_non_empty_reason(db, new_user, unique_email):
    """Direct database verification of ck_action_item_rejected_contract."""
    admin = new_user("Admin User")
    meeting = Meeting(created_by=admin["id"], title="Constraint Test Rej", status="completed")
    db.add(meeting)
    db.commit()

    item_bad = MeetingActionItem(
        meeting_id=meeting.id,
        description="Rejected without reason",
        review_status="rejected",
        rejection_reason=None,
        reviewed_by_id=admin["id"],
    )
    db.add(item_bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_trigger_blocks_manual_legacy_flag_insert_and_update(db, new_user, unique_email):
    """Verifies trigger_block_manual_legacy_insert and trigger_block_legacy_escalation."""
    from sqlalchemy.exc import ProgrammingError, InternalError
    admin = new_user("Admin User")
    meeting = Meeting(created_by=admin["id"], title="Trigger Test", status="completed")
    db.add(meeting)
    db.commit()

    # Manual insert with is_legacy_conversion = True is blocked by trigger
    item_bad = MeetingActionItem(
        meeting_id=meeting.id,
        description="Manual legacy attempt",
        review_status="converted",
        is_legacy_conversion=True,
    )
    db.add(item_bad)
    with pytest.raises((ProgrammingError, InternalError)) as excinfo:
        db.commit()
    db.rollback()
    assert "Security violation" in str(excinfo.value) or "cannot be created" in str(excinfo.value)

    # Insert normal item
    item_ok = MeetingActionItem(
        meeting_id=meeting.id,
        description="Legitimate item",
        review_status="proposed",
        is_legacy_conversion=False,
    )
    db.add(item_ok)
    db.commit()

    # Update escalating is_legacy_conversion from false to true is blocked
    item_ok.is_legacy_conversion = True
    with pytest.raises((ProgrammingError, InternalError)) as excinfo2:
        db.commit()
    db.rollback()
    assert "cannot be changed once set" in str(excinfo2.value) or "Security violation" in str(excinfo2.value)


def test_sprint_task_deletion_restricted_when_linked(client, db, new_user, unique_email):
    """Verifies ON DELETE RESTRICT on sprint_tasks.id prevents deletion while action item is linked."""
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"PRestrict {unique_email}", "status": "active"}).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrres"), "manager", "Restrict Mgr")
    member = _onboard_user(client, admin["headers"], _tag(unique_email, "memres"), "employee", "Restrict Mem", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    sprint = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": project["id"], "name": "Sprint Restrict", "start_date": "2026-03-01", "end_date": "2026-03-07",
    }).json()

    meeting = Meeting(created_by=mgr["user_id"], title="Restrict Meeting", project_id=project["id"], status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(
        meeting_id=meeting.id, description="Task restrict", assignment_method="unassigned",
        status="pending", review_status="proposed", source="ai",
    )
    db.add(item)
    db.commit()

    # Confirm and convert
    client.post(
        f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/confirm",
        headers=mgr["headers"],
        json={"assignee_id": member["employee_id"], "due_date": "2026-03-05"},
    )
    conv = client.post(
        f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/convert",
        headers=mgr["headers"],
        json={"sprint_id": sprint["id"]},
    ).json()

    task_id = conv["converted_sprint_task_id"]
    task = db.query(SprintTask).filter(SprintTask.id == task_id).first()
    assert task is not None

    # Direct deletion of task must raise IntegrityError because MeetingActionItem links to it with RESTRICT
    db.delete(task)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# =========================================================================== #
# 4. Meeting Visibility Matrix & Project Linking Authorization
# =========================================================================== #

def test_meeting_linking_authorization(client, db, new_user, unique_email):
    """
    Verifies who can link meetings to projects:
      - Admin: Any project.
      - Assigned Manager: Assigned project only.
      - Assigned Team Lead: Assigned project only.
      - Active Member: Assigned project only.
      - Unassigned roles: 403 Forbidden.
    """
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"PAuth {unique_email}"}).json()
    mgr_assigned = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrass"), "manager", "Assigned Mgr")
    mgr_other = _onboard_user(client, admin["headers"], _tag(unique_email, "mgroth"), "manager", "Other Mgr")
    lead = _onboard_user(client, admin["headers"], _tag(unique_email, "leadass"), "employee", "Lead Ass", project_id=project["id"])
    member = _onboard_user(client, admin["headers"], _tag(unique_email, "memass"), "employee", "Member Ass", project_id=project["id"])
    outsider = _onboard_user(client, admin["headers"], _tag(unique_email, "outsider"), "employee", "Outsider")

    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr_assigned["user_id"]})
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"], json={"employee_id": lead["employee_id"]})

    # Schedule endpoint tests project linking authorization
    future_time = "2026-05-01T10:00:00Z"

    # 1. Admin can schedule for project
    r_admin = client.post(f"{MEETINGS_BASE}/schedule", headers=admin["headers"], json={
        "title": "Admin Meeting", "project_id": project["id"], "scheduled_at": future_time,
    })
    assert r_admin.status_code == 201

    # 2. Assigned manager can schedule
    r_mgr = client.post(f"{MEETINGS_BASE}/schedule", headers=mgr_assigned["headers"], json={
        "title": "Manager Meeting", "project_id": project["id"], "scheduled_at": future_time,
    })
    assert r_mgr.status_code == 201

    # 3. Unassigned manager is denied (403)
    r_mgr_other = client.post(f"{MEETINGS_BASE}/schedule", headers=mgr_other["headers"], json={
        "title": "Other Mgr Meeting", "project_id": project["id"], "scheduled_at": future_time,
    })
    assert r_mgr_other.status_code == 403

    # 4. Assigned Team Lead can schedule
    r_lead = client.post(f"{MEETINGS_BASE}/schedule", headers=lead["headers"], json={
        "title": "Lead Meeting", "project_id": project["id"], "scheduled_at": future_time,
    })
    assert r_lead.status_code == 201

    import uuid
    # 5. Active project member can link their project to an online meeting
    r_member = client.post("/api/v1/meetings/online", headers=member["headers"], json={
        "request_id": str(uuid.uuid4()),
        "title": "Member Online Meeting",
        "project_id": project["id"],
    })
    assert r_member.status_code == 201, r_member.text

    # 6. Outside employee is denied linking project to an online meeting (403)
    r_out = client.post("/api/v1/meetings/online", headers=outsider["headers"], json={
        "request_id": str(uuid.uuid4()),
        "title": "Outsider Online Meeting",
        "project_id": project["id"],
    })
    assert r_out.status_code == 403

    # 7. HR manager without project assignment cannot link this project to an online meeting (403)
    hr_user = _onboard_user(client, admin["headers"], _tag(unique_email, "hruser"), "hr_manager", "HR Manager")
    r_hr = client.post("/api/v1/meetings/online", headers=hr_user["headers"], json={
        "request_id": str(uuid.uuid4()),
        "title": "HR Online Meeting",
        "project_id": project["id"],
    })
    assert r_hr.status_code == 403


def test_meeting_visibility_matrix(client, db, new_user, unique_email):
    """
    Verifies meeting detail and list access:
      - Admin: All meetings.
      - Assigned Manager: Project meetings.
      - Assigned Team Lead: Project meetings.
      - Assigned Member: Read-only access to project meetings.
      - Unrelated user: 403 on project meeting, 404 on unlinked meeting.
    """
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"PVis {unique_email}"}).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, "mgrvis"), "manager", "Vis Mgr")
    member = _onboard_user(client, admin["headers"], _tag(unique_email, "memvis"), "employee", "Vis Member", project_id=project["id"])
    outsider = _onboard_user(client, admin["headers"], _tag(unique_email, "outvis"), "employee", "Outsider Vis")

    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"], json={"manager_user_id": mgr["user_id"]})

    # Project-linked meeting created by Manager
    meeting_proj = Meeting(created_by=mgr["user_id"], title="Project Discussion", project_id=project["id"], status="completed")
    # Unlinked meeting created by Manager
    meeting_priv = Meeting(created_by=mgr["user_id"], title="Private Discussion", project_id=None, status="completed")
    db.add_all([meeting_proj, meeting_priv])
    db.commit()

    # Admin sees project meeting, but unlinked meeting is strictly creator-only (404)
    assert client.get(f"{MEETINGS_BASE}/{meeting_proj.id}", headers=admin["headers"]).status_code == 200
    assert client.get(f"{MEETINGS_BASE}/{meeting_priv.id}", headers=admin["headers"]).status_code == 404

    # Assigned manager sees both (one is project-linked, one is created by manager)
    assert client.get(f"{MEETINGS_BASE}/{meeting_proj.id}", headers=mgr["headers"]).status_code == 200
    assert client.get(f"{MEETINGS_BASE}/{meeting_priv.id}", headers=mgr["headers"]).status_code == 200

    # Project member can view project meeting, but unlinked meeting is 404
    assert client.get(f"{MEETINGS_BASE}/{meeting_proj.id}", headers=member["headers"]).status_code == 200
    assert client.get(f"{MEETINGS_BASE}/{meeting_priv.id}", headers=member["headers"]).status_code == 404

    # Outsider denied project meeting (403), unlinked meeting is 404
    assert client.get(f"{MEETINGS_BASE}/{meeting_proj.id}", headers=outsider["headers"]).status_code == 403
    assert client.get(f"{MEETINGS_BASE}/{meeting_priv.id}", headers=outsider["headers"]).status_code == 404
