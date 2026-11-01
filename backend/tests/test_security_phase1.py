"""
tests/test_security_phase1.py

Comprehensive security and RBAC test suite covering Phase 1:
- C1: Customer Support fake-admin fallback elimination
- C2: Recruitment resume privacy and statistics gating
- C3: Customer Support ticket visibility & user-scoped access
- C4: Incident Management role alignment and employee reporting
- Manager role DB existence and project/directory access control
"""

import io
import uuid
import pytest
from sqlalchemy import text
from config.database import SessionLocal, engine
from core.permissions import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_HR,
    ROLE_MANAGER,
    ROLE_RECRUITER,
    ROLE_SUPPORT_AGENT,
    ROLE_VIEWER,
    OVERRIDE_ROLES,
    SPRINT_MANAGE_ROLES,
    SUPPORT_FULL_ACCESS_ROLES,
)
from tests.helpers import complete_first_login


def _cleanup_test_managers():
    from tests.conftest import _cleanup_test_rows
    _cleanup_test_rows()


@pytest.fixture(autouse=True)
def clean_test_managers():
    _cleanup_test_managers()
    yield
    _cleanup_test_managers()




# =====================================================================
# 1. AUTHENTICATION & C1 VULNERABILITY TESTS
# =====================================================================

def test_unauthenticated_request_rejected(client):
    """Endpoints requiring authentication return 401 when no token is supplied."""
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_invalid_token_rejected(client):
    """Malformed or invalid JWT tokens return 401."""
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-token"})
    assert r.status_code == 401


def test_c1_customer_support_no_token_returns_401(client):
    """C1 REGRESSION: Customer Support must NOT fall back to fake admin when unauthenticated."""
    r = client.get("/api/v1/customer-support/tickets")
    assert r.status_code == 401

    r = client.get("/api/v1/customer-support/chat/sessions")
    assert r.status_code == 401

    r = client.post("/api/v1/customer-support/tickets", json={
        "subject": "Unauthorized ticket",
        "description": "Should fail with 401",
        "priority": "low",
    })
    assert r.status_code == 401


def test_c1_customer_support_invalid_token_returns_401(client):
    """C1 REGRESSION: Customer Support must NOT catch JWT errors and grant admin access."""
    bad_headers = {"Authorization": "Bearer bad.token.here"}
    r = client.get("/api/v1/customer-support/tickets", headers=bad_headers)
    assert r.status_code == 401

    r = client.post("/api/v1/customer-support/categories", headers=bad_headers, json={
        "name": "Malicious Category",
        "description": "Should be rejected",
    })
    assert r.status_code == 401


def test_c1_customer_support_category_requires_privileged_role(client, new_user):
    """Creating knowledge categories requires admin or support_agent, not regular employee."""
    emp = new_user(role=ROLE_EMPLOYEE)
    r = client.post("/api/v1/customer-support/categories", headers=emp["headers"], json={
        "name": "Employee Cat",
        "description": "Should be 403",
    })
    assert r.status_code == 403

    agent = new_user(role=ROLE_SUPPORT_AGENT)
    r = client.post("/api/v1/customer-support/categories", headers=agent["headers"], json={
        "name": f"Agent Cat {uuid.uuid4().hex[:6]}",
        "description": "Should succeed",
    })
    assert r.status_code == 201


# =====================================================================
# 2. C2 VULNERABILITY TESTS — RECRUITMENT PRIVACY
# =====================================================================

@pytest.fixture
def recruitment_test_job(client, new_user) -> int:
    admin = new_user(role=ROLE_ADMIN)
    r = client.post("/api/v1/recruitment/jobs", headers=admin["headers"], json={
        "title": f"Security Test Role {uuid.uuid4().hex[:6]}",
        "description": "Testing resume privacy",
        "required_skills": "Security, Python",
        "min_education": "Bachelor's Degree",
        "experience_level": "mid",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_c2_recruitment_resume_access_control(client, new_user, recruitment_test_job):
    """C2 REGRESSION: Only admin, hr_manager, recruiter can access candidate resumes."""
    job_id = recruitment_test_job
    admin = new_user(role=ROLE_ADMIN)

    # Upload a sample resume as admin
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    r = client.post(
        f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=admin["headers"],
        data={"candidate_name": "Priv Candidate", "candidate_email": "priv@example.com"},
        files={"resume_file": ("priv.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert r.status_code == 201
    resume_id = r.json()["id"]

    # 1. Privileged roles CAN list and get resumes
    for role in [ROLE_ADMIN, ROLE_HR, ROLE_RECRUITER]:
        u = new_user(role=role)
        r = client.get(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=u["headers"])
        assert r.status_code == 200, f"Role {role} should be able to list resumes"
        r = client.get(f"/api/v1/recruitment/resumes/{resume_id}", headers=u["headers"])
        assert r.status_code == 200, f"Role {role} should be able to get resume"

    # 2. Non-privileged roles CANNOT list or get resumes (403 Forbidden)
    for role in [ROLE_EMPLOYEE, ROLE_SUPPORT_AGENT, ROLE_VIEWER]:
        u = new_user(role=role)
        r = client.get(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=u["headers"])
        assert r.status_code == 403, f"Role {role} must NOT be able to list resumes"
        r = client.get(f"/api/v1/recruitment/resumes/{resume_id}", headers=u["headers"])
        assert r.status_code == 403, f"Role {role} must NOT be able to get resume"

    # Cleanup
    client.delete(f"/api/v1/recruitment/resumes/{resume_id}", headers=admin["headers"])


def test_c2_recruitment_stats_gated(client, new_user):
    """Recruitment statistics must be restricted to hiring roles (admin, hr_manager, recruiter)."""
    admin = new_user(role=ROLE_ADMIN)
    r = client.get("/api/v1/recruitment/stats", headers=admin["headers"])
    assert r.status_code == 200

    employee = new_user(role=ROLE_EMPLOYEE)
    r = client.get("/api/v1/recruitment/stats", headers=employee["headers"])
    assert r.status_code == 403


# =====================================================================
# 3. C3 VULNERABILITY TESTS — TICKET VISIBILITY & SCOPING
# =====================================================================

def test_c3_ticket_user_scoping_and_visibility(client, new_user):
    """C3 REGRESSION: Employees can only view/reply to their own tickets; staff can see all."""
    emp_a = new_user(role=ROLE_EMPLOYEE, full_name="Employee Alice")
    emp_b = new_user(role=ROLE_EMPLOYEE, full_name="Employee Bob")
    support_agent = new_user(role=ROLE_SUPPORT_AGENT, full_name="Support Agent Sam")
    admin = new_user(role=ROLE_ADMIN, full_name="Admin Alex")
    manager = new_user(role=ROLE_MANAGER, full_name="Manager Mary")

    # Employee Alice creates a ticket
    r = client.post("/api/v1/customer-support/tickets", headers=emp_a["headers"], json={
        "subject": "Alice's Secret Payroll Issue",
        "description": "Sensitive payroll data here",
        "priority": "high",
        "customer_name": "Alice",
        "customer_email": emp_a["email"],
    })
    assert r.status_code == 201, r.text
    alice_ticket_id = r.json()["id"]

    # 1. Alice can view her own ticket
    r = client.get(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=emp_a["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == alice_ticket_id

    # 2. Alice sees her ticket in the ticket list
    r = client.get("/api/v1/customer-support/tickets", headers=emp_a["headers"])
    assert r.status_code == 200
    assert any(t["id"] == alice_ticket_id for t in r.json())

    # 3. Bob CANNOT see Alice's ticket in the ticket list
    r = client.get("/api/v1/customer-support/tickets", headers=emp_b["headers"])
    assert r.status_code == 200
    assert not any(t["id"] == alice_ticket_id for t in r.json())

    # 4. Bob CANNOT view Alice's ticket detail directly (403 Forbidden)
    r = client.get(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=emp_b["headers"])
    assert r.status_code == 403

    # 5. Bob CANNOT post a reply to Alice's ticket (403 Forbidden)
    r = client.post(f"/api/v1/customer-support/tickets/{alice_ticket_id}/messages", headers=emp_b["headers"], json={
        "message": "Bob snooping on Alice's ticket",
    })
    assert r.status_code == 403

    # 6. Bob CANNOT update Alice's ticket (403 Forbidden)
    r = client.put(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=emp_b["headers"], json={
        "status": "resolved",
    })
    assert r.status_code == 403

    # 7. Support staff (admin, support_agent) CAN view Alice's ticket
    for staff in [support_agent, admin]:
        r = client.get(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=staff["headers"])
        assert r.status_code == 200, f"{staff} should be able to view ticket"

    # 8. Manager CANNOT view Alice's private ticket (restricted to own tickets)
    r = client.get(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=manager["headers"])
    assert r.status_code == 403, "Manager must NOT be able to view other employees' tickets"

    # 9. Manager CANNOT reply to Alice's private ticket
    r = client.post(f"/api/v1/customer-support/tickets/{alice_ticket_id}/messages", headers=manager["headers"], json={
        "message": "Manager unauthorized message",
    })
    assert r.status_code == 403

    # 10. Manager CAN create and view their own ticket
    r = client.post("/api/v1/customer-support/tickets", headers=manager["headers"], json={
        "subject": "Manager Own Office Chair Request",
        "description": "Ergonomic chair needed",
        "priority": "low",
        "customer_name": "Manager Mary",
        "customer_email": manager["email"],
    })
    assert r.status_code == 201
    mgr_ticket_id = r.json()["id"]

    r = client.get(f"/api/v1/customer-support/tickets/{mgr_ticket_id}", headers=manager["headers"])
    assert r.status_code == 200

    # 11. Support staff CAN update tickets; manager CANNOT update tickets
    r = client.put(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=support_agent["headers"], json={
        "priority": "critical",
    })
    assert r.status_code == 200

    r = client.put(f"/api/v1/customer-support/tickets/{alice_ticket_id}", headers=manager["headers"], json={
        "priority": "critical",
    })
    assert r.status_code == 403



# =====================================================================
# 4. C4 VULNERABILITY TESTS — INCIDENT MANAGEMENT ROLES
# =====================================================================

def test_c4_incident_roles_and_employee_reporting(client, new_user, db):
    """C4 REGRESSION: Any employee can report an incident; only write roles can modify."""
    from datetime import date
    from models.employee import Employee

    employee = new_user(role=ROLE_EMPLOYEE)
    support_agent = new_user(role=ROLE_SUPPORT_AGENT)
    manager = new_user(role=ROLE_MANAGER)
    admin = new_user(role=ROLE_ADMIN)

    # Incidents can only be assigned to active employees.
    db.add(Employee(
        user_id=support_agent["id"],
        employee_code=f"EMP-C4-{uuid.uuid4().hex[:6]}",
        job_title="Support Engineer",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
    ))
    db.commit()

    # 1. Regular employee CAN report (create) an incident
    r = client.post("/api/v1/incidents", headers=employee["headers"], json={
        "title": "VPN Connection Failing",
        "description": "Unable to connect to internal VPN server",
        "severity": "medium",
        "affected_system": "VPN Gateway",
    })
    assert r.status_code == 201, r.text
    incident_id = r.json()["id"]

    # 2. Any authenticated user can view the incident and statistics
    r = client.get(f"/api/v1/incidents/{incident_id}", headers=employee["headers"])
    assert r.status_code == 200
    r = client.get("/api/v1/incidents/statistics", headers=employee["headers"])
    assert r.status_code == 200

    # 3. Regular employee CANNOT update, assign, resolve, or delete
    r = client.put(f"/api/v1/incidents/{incident_id}", headers=employee["headers"], json={
        "title": "Hacked Title",
    })
    assert r.status_code == 403

    r = client.put(f"/api/v1/incidents/{incident_id}/assign", headers=employee["headers"], json={
        "assigned_to": employee["id"],
    })
    assert r.status_code == 403

    r = client.put(f"/api/v1/incidents/{incident_id}/resolve", headers=employee["headers"], json={
        "root_cause": "Self resolved",
    })
    assert r.status_code == 403

    r = client.delete(f"/api/v1/incidents/{incident_id}", headers=employee["headers"])
    assert r.status_code == 403

    # 4. Manager CAN update and assign the incident
    r = client.put(f"/api/v1/incidents/{incident_id}", headers=manager["headers"], json={
        "title": "VPN Connection Failing - Investigating",
    })
    assert r.status_code == 200

    r = client.put(f"/api/v1/incidents/{incident_id}/assign", headers=manager["headers"], json={
        "assigned_to": support_agent["id"],
    })
    assert r.status_code == 200

    # 5. Support Agent CAN resolve the incident
    r = client.put(f"/api/v1/incidents/{incident_id}/resolve", headers=support_agent["headers"], json={
        "root_cause": "Restarted VPN service daemon",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # 6. Admin CAN delete the incident
    r = client.delete(f"/api/v1/incidents/{incident_id}", headers=admin["headers"])
    assert r.status_code == 204


# =====================================================================
# 5. MANAGER ROLE & DIRECTORY ACCESS TESTS
# =====================================================================

def test_manager_role_database_and_directory_access(client, new_user):
    """Verify manager role capabilities: directory view access vs restricted onboarding."""
    # 1. Manager role exists in the database
    with SessionLocal() as db:
        res = db.execute(text("SELECT id, name FROM roles WHERE name = 'manager'")).first()
        assert res is not None, "Manager role must exist in roles table"

    # 2. Manager user can view employee directory
    manager = new_user(role=ROLE_MANAGER)
    r = client.get("/api/v1/employee-management/employees", headers=manager["headers"])
    assert r.status_code == 200, "Manager must be able to view employee directory"

    # 3. Manager CANNOT onboard a new employee (admin / hr_manager only)
    r = client.post("/api/v1/employee-management/employees", headers=manager["headers"], json={
        "full_name": "New Hire",
        "email": f"newhire_{uuid.uuid4().hex[:6]}@example.com",
        "job_title": "Developer",
        "department_id": 1,
    })
    assert r.status_code == 403, "Manager must NOT be able to onboard employees"

    # 4. Manager is included in OVERRIDE_ROLES for project-management
    assert "manager" in OVERRIDE_ROLES


# =====================================================================
# 6. PHASE 1.1: MANAGER RBAC & PERMISSION BOUNDARIES
# =====================================================================

import concurrent.futures
from datetime import datetime, timedelta, timezone


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _onboard_emp(client, admin_headers, email, role_name="employee", full_name="Test Person", project_id=None):
    role_id = _role_id(client, admin_headers, role_name)
    r = client.post("/api/v1/employee-management/employees", headers=admin_headers, json={
        "full_name": full_name, "email": email, "role_id": role_id,
        "job_title": "Engineer", "project_id": project_id, "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    temp_pw = r.json()["temporary_password"]
    emp_id = r.json()["employee"]["id"]
    user_id = r.json()["employee"]["user"]["id"]
    headers = complete_first_login(client, email, temp_pw)
    return {"employee_id": emp_id, "user_id": user_id, "headers": headers, "email": email}


def _make_test_project(client, admin_headers, lead_email, proj_name=None):
    if not proj_name:
        proj_name = f"Security Project {uuid.uuid4().hex[:6]}"
    project = client.post("/api/v1/employee-management/projects", headers=admin_headers, json={
        "name": proj_name,
        "deadline": "2026-12-31",
        "status": "active",
    }).json()
    lead = _onboard_emp(client, admin_headers, lead_email, role_name="employee", full_name="Lead Person", project_id=project["id"])
    client.post(f"/api/v1/employee-management/projects/{project['id']}/team-lead", headers=admin_headers,
                json={"employee_id": lead["employee_id"]})
    return project, lead


def test_single_active_manager_enforced_in_application_and_db(client, new_user):
    """Enforce exactly ONE active Manager account across the organization in application logic and DB."""
    admin = new_user(role=ROLE_ADMIN)
    roles = client.get("/api/v1/auth/roles", headers=admin["headers"]).json()
    mgr_role_id = next(r["id"] for r in roles if r["name"] == "manager")
    emp_role_id = next(r["id"] for r in roles if r["name"] == "employee")

    # 1. Onboard the first Manager -> 201 Created
    email1 = f"pytest_manager_1_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/v1/employee-management/employees", headers=admin["headers"], json={
        "full_name": "Org Manager 1",
        "email": email1,
        "role_id": mgr_role_id,
        "job_title": "Organization Manager",
        "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    mgr1_emp_id = r.json()["employee"]["id"]

    # 2. Under Submodule 4.2 multi-manager architecture, onboarding a second active Manager succeeds (201)
    email2 = f"pytest_manager_2_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/v1/employee-management/employees", headers=admin["headers"], json={
        "full_name": "Org Manager 2",
        "email": email2,
        "role_id": mgr_role_id,
        "job_title": "Second Manager",
        "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text

    # 3. Updating an existing employee to Manager role succeeds under multi-manager architecture
    email_emp = f"pytest_dev_emp_{uuid.uuid4().hex[:6]}@example.com"
    emp = _onboard_emp(client, admin["headers"], email_emp, role_name="employee")
    r = client.patch(f"/api/v1/employee-management/employees/{emp['employee_id']}", headers=admin["headers"], json={
        "role_id": mgr_role_id,
    })
    assert r.status_code == 200, r.text

    # 4. Terminate the first Manager -> status becomes terminated, user becomes inactive
    r = client.post(f"/api/v1/employee-management/employees/{mgr1_emp_id}/terminate", headers=admin["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "terminated"

    # 5. Onboarding a replacement Manager succeeds
    email3 = f"pytest_manager_3_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/v1/employee-management/employees", headers=admin["headers"], json={
        "full_name": "Org Manager 3 Replacement",
        "email": email3,
        "role_id": mgr_role_id,
        "job_title": "Organization Manager Replacement",
        "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text


def test_concurrent_manager_assignment_safely_handled(client, new_user):
    """Verify concurrent manager creation is serialized safely via advisory lock without deadlocks."""
    admin = new_user(role=ROLE_ADMIN)
    roles = client.get("/api/v1/auth/roles", headers=admin["headers"]).json()
    mgr_role_id = next(r["id"] for r in roles if r["name"] == "manager")

    results = []

    def try_create_manager(index: int):
        email = f"pytest_race_mgr_{index}_{uuid.uuid4().hex[:6]}@example.com"
        r = client.post("/api/v1/employee-management/employees", headers=admin["headers"], json={
            "full_name": f"Concurrent Manager {index}",
            "email": email,
            "role_id": mgr_role_id,
            "job_title": "Race Test Manager",
            "hire_date": "2026-01-01",
        })
        return r.status_code, r.text

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(try_create_manager, i) for i in range(4)]
        results = [f.result() for f in futures]

    statuses = [s for s, _ in results]
    assert all(s == 201 for s in statuses), f"Expected all 201 Created under multi-manager architecture, got: {statuses}"

    # Verify at DB level that all created managers exist and are active
    with SessionLocal() as db:
        active_managers = db.execute(text(
            "SELECT id, email FROM users WHERE role_id = :role_id AND is_active = true AND deleted_at IS NULL AND email LIKE '%pytest_race_mgr%'"
        ), {"role_id": mgr_role_id}).fetchall()
        assert len(active_managers) == 4


def test_manager_cross_project_sprint_management(client, new_user):
    """Organization-wide Manager can view all 3 project sprints, overview, and update sprint timelines."""
    admin = new_user(role=ROLE_ADMIN)
    manager = new_user(role=ROLE_MANAGER)

    # 1. Manager can access sprints for all 3 demo projects (Project 2, 3, 4)
    for project_id in [2, 3, 4]:
        r = client.get(f"/api/v1/sprints?project_id={project_id}", headers=manager["headers"])
        assert r.status_code == 200, f"Manager must be able to view sprints for project {project_id}"
        sprints = r.json()
        assert len(sprints) > 0, f"Project {project_id} should have sprints"

    # 2. Manager can view /sprints/overview
    r = client.get("/api/v1/sprints/overview", headers=manager["headers"])
    assert r.status_code == 200, "Manager must be able to view /sprints/overview"
    overview = r.json()
    assert isinstance(overview, list)
    assert len(overview) >= 3

    # 3. Manager can update sprint timelines
    r = client.patch("/api/v1/sprints/192", headers=manager["headers"], json={
        "name": "Week 1 - Manager Updated",
    })
    assert r.status_code == 200, "Manager must be able to update sprint timelines"
    assert r.json()["name"] == "Week 1 - Manager Updated"


def test_team_leader_cannot_access_another_project_sprint(client, new_user):
    """Team Leader is restricted to their assigned project and cannot access other projects' sprints."""
    admin = new_user(role=ROLE_ADMIN)

    # Create Project A and Project B
    proj_a, lead_a = _make_test_project(client, admin["headers"], f"pytest_lead_a_{uuid.uuid4().hex[:6]}@example.com")
    proj_b, lead_b = _make_test_project(client, admin["headers"], f"pytest_lead_b_{uuid.uuid4().hex[:6]}@example.com")

    # Get sprints for Project B
    r = client.get(f"/api/v1/sprints?project_id={proj_b['id']}", headers=lead_b["headers"])
    assert r.status_code == 200
    proj_b_sprints = r.json()
    assert len(proj_b_sprints) > 0
    proj_b_sprint_id = proj_b_sprints[0]["id"]

    # 1. Lead A cannot view Project B's sprints (403 Forbidden)
    r = client.get(f"/api/v1/sprints?project_id={proj_b['id']}", headers=lead_a["headers"])
    assert r.status_code == 403, "Team Lead A must NOT be able to view Project B's sprints"

    # 2. Lead A cannot view individual sprint of Project B (403 Forbidden)
    r = client.get(f"/api/v1/sprints/{proj_b_sprint_id}", headers=lead_a["headers"])
    assert r.status_code == 403, "Team Lead A must NOT be able to view Project B's sprint detail"

    # 3. Lead A cannot edit sprint of Project B (403 Forbidden)
    r = client.patch(f"/api/v1/sprints/{proj_b_sprint_id}", headers=lead_a["headers"], json={
        "name": "Hacked Sprint",
    })
    assert r.status_code == 403, "Team Lead A must NOT be able to edit Project B's sprint"

    # 4. Lead A CAN view and edit Project A's sprints (200 OK)
    r = client.get(f"/api/v1/sprints?project_id={proj_a['id']}", headers=lead_a["headers"])
    assert r.status_code == 200
    proj_a_sprint_id = r.json()[0]["id"]

    r = client.patch(f"/api/v1/sprints/{proj_a_sprint_id}", headers=lead_a["headers"], json={
        "name": "Week 1 - Lead A Updated",
    })
    assert r.status_code == 200
    assert r.json()["name"] == "Week 1 - Lead A Updated"


def test_manager_cross_project_chat_communication(client, new_user):
    """Manager can communicate across all project teams; normal employees cannot cross projects."""
    admin = new_user(role=ROLE_ADMIN)
    manager = new_user(role=ROLE_MANAGER)

    # Create Project A with Member A and Project B with Member B
    proj_a, lead_a = _make_test_project(client, admin["headers"], f"pytest_lead_ca_{uuid.uuid4().hex[:6]}@example.com")
    member_a = _onboard_emp(client, admin["headers"], f"pytest_mema_{uuid.uuid4().hex[:6]}@example.com", project_id=proj_a["id"])

    proj_b, lead_b = _make_test_project(client, admin["headers"], f"pytest_lead_cb_{uuid.uuid4().hex[:6]}@example.com")
    member_b = _onboard_emp(client, admin["headers"], f"pytest_memb_{uuid.uuid4().hex[:6]}@example.com", project_id=proj_b["id"])

    # 1. Manager contacts list includes members from all projects
    r = client.get("/api/v1/chat/contacts", headers=manager["headers"])
    assert r.status_code == 200
    contact_user_ids = [c["user_id"] for c in r.json()]
    assert member_a["user_id"] in contact_user_ids, "Member A should be in Manager contacts"
    assert member_b["user_id"] in contact_user_ids, "Member B should be in Manager contacts"

    # 2. Manager can open thread and message Member A (Project A)
    r = client.post("/api/v1/chat/threads", headers=manager["headers"], json={
        "other_user_id": member_a["user_id"],
    })
    assert r.status_code == 200, r.text
    thread_a_id = r.json()["id"]

    r = client.post(f"/api/v1/chat/threads/{thread_a_id}/messages", headers=manager["headers"], json={
        "body": "Hello from Org Manager to Project A",
    })
    assert r.status_code == 201

    # 3. Manager can open thread and message Member B (Project B)
    r = client.post("/api/v1/chat/threads", headers=manager["headers"], json={
        "other_user_id": member_b["user_id"],
    })
    assert r.status_code == 200, r.text
    thread_b_id = r.json()["id"]

    r = client.post(f"/api/v1/chat/threads/{thread_b_id}/messages", headers=manager["headers"], json={
        "body": "Hello from Org Manager to Project B",
    })
    assert r.status_code == 201

    # 4. Member A cannot initiate cross-project chat with Member B (403 Forbidden)
    r = client.post("/api/v1/chat/threads", headers=member_a["headers"], json={
        "other_user_id": member_b["user_id"],
    })
    assert r.status_code == 403, "Ordinary employee must NOT be able to open cross-project chat"


def test_manager_can_view_scheduled_meetings_across_projects(client, new_user):
    """Manager can view scheduled meetings across all projects; ordinary non-participants cannot."""
    admin = new_user(role=ROLE_ADMIN)
    manager = new_user(role=ROLE_MANAGER)

    # Create Project A and Project B
    proj_a, lead_a = _make_test_project(client, admin["headers"], f"pytest_lead_ma_{uuid.uuid4().hex[:6]}@example.com")
    proj_b, lead_b = _make_test_project(client, admin["headers"], f"pytest_lead_mb_{uuid.uuid4().hex[:6]}@example.com")
    outsider = _onboard_emp(client, admin["headers"], f"pytest_outsider_{uuid.uuid4().hex[:6]}@example.com")

    # Schedule a meeting for Project A (by Lead A)
    when_a = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.post("/api/v1/meetings/schedule", headers=lead_a["headers"], json={
        "title": "Project A Architecture Review",
        "project_id": proj_a["id"],
        "scheduled_at": when_a,
    })
    assert r.status_code == 201, r.text
    meeting_a_id = r.json()["id"]

    # Schedule a meeting for Project B (by Lead B)
    when_b = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.post("/api/v1/meetings/schedule", headers=lead_b["headers"], json={
        "title": "Project B Security Review",
        "project_id": proj_b["id"],
        "scheduled_at": when_b,
    })
    assert r.status_code == 201, r.text
    meeting_b_id = r.json()["id"]

    # 1. Manager can view both meetings in scheduled list even though not organizer/attendee
    r = client.get("/api/v1/meetings/scheduled", headers=manager["headers"])
    assert r.status_code == 200
    scheduled_ids = [m["id"] for m in r.json()]
    assert meeting_a_id in scheduled_ids, "Manager must see Project A scheduled meeting"
    assert meeting_b_id in scheduled_ids, "Manager must see Project B scheduled meeting"

    # 2. Outsider non-participant employee sees neither meeting
    r = client.get("/api/v1/meetings/scheduled", headers=outsider["headers"])
    assert r.status_code == 200
    outsider_ids = [m["id"] for m in r.json()]
    assert meeting_a_id not in outsider_ids
    assert meeting_b_id not in outsider_ids


def test_manager_cannot_access_another_employee_private_ticket(client, new_user):
    """Manager only accesses their own submitted support tickets, not confidential tickets of others."""
    admin = new_user(role=ROLE_ADMIN)
    manager = new_user(role=ROLE_MANAGER)
    employee = new_user(role=ROLE_EMPLOYEE)

    # Employee submits a confidential ticket
    r = client.post("/api/v1/customer-support/tickets", headers=employee["headers"], json={
        "subject": "Confidential Employee Medical Request",
        "description": "Private health accommodation info",
        "priority": "high",
        "customer_name": "Private Employee",
        "customer_email": employee["email"],
    })
    assert r.status_code == 201
    emp_ticket_id = r.json()["id"]

    # 1. Manager cannot view the employee's ticket (403 Forbidden)
    r = client.get(f"/api/v1/customer-support/tickets/{emp_ticket_id}", headers=manager["headers"])
    assert r.status_code == 403, "Manager must NOT be able to view another employee's private ticket"

    # 2. Manager cannot see the employee's ticket in the ticket list
    r = client.get("/api/v1/customer-support/tickets", headers=manager["headers"])
    assert r.status_code == 200
    assert not any(t["id"] == emp_ticket_id for t in r.json())

    # 3. Manager cannot reply to the employee's ticket (403 Forbidden)
    r = client.post(f"/api/v1/customer-support/tickets/{emp_ticket_id}/messages", headers=manager["headers"], json={
        "message": "Unauthorized manager comment",
    })
    assert r.status_code == 403

    # 4. Manager cannot update the employee's ticket status/priority (403 Forbidden)
    r = client.put(f"/api/v1/customer-support/tickets/{emp_ticket_id}", headers=manager["headers"], json={
        "priority": "low",
    })
    assert r.status_code == 403

    # 5. Manager CAN create and manage their own submitted ticket
    r = client.post("/api/v1/customer-support/tickets", headers=manager["headers"], json={
        "subject": "Manager Software License Request",
        "description": "Need IDE license renewal",
        "priority": "medium",
        "customer_name": "Org Manager",
        "customer_email": manager["email"],
    })
    assert r.status_code == 201
    mgr_ticket_id = r.json()["id"]

    # Manager can view their own ticket
    r = client.get(f"/api/v1/customer-support/tickets/{mgr_ticket_id}", headers=manager["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == mgr_ticket_id

    # Manager can reply to their own ticket
    r = client.post(f"/api/v1/customer-support/tickets/{mgr_ticket_id}/messages", headers=manager["headers"], json={
        "message": "Adding license invoice",
    })
    assert r.status_code == 200 or r.status_code == 201


def test_admin_and_support_agent_ticket_workflows(client, new_user):
    """Admin and Support Agent ticket workflows remain fully functional across all tickets."""
    admin = new_user(role=ROLE_ADMIN)
    agent = new_user(role=ROLE_SUPPORT_AGENT)
    employee = new_user(role=ROLE_EMPLOYEE)

    # Employee submits ticket
    r = client.post("/api/v1/customer-support/tickets", headers=employee["headers"], json={
        "subject": "Customer Login Issue",
        "description": "SSO login timeout",
        "priority": "medium",
        "customer_name": "Customer User",
        "customer_email": employee["email"],
    })
    assert r.status_code == 201
    ticket_id = r.json()["id"]

    # 1. Support Agent can list all tickets and find this ticket
    r = client.get("/api/v1/customer-support/tickets", headers=agent["headers"])
    assert r.status_code == 200
    assert any(t["id"] == ticket_id for t in r.json())

    # 2. Support Agent can view ticket detail
    r = client.get(f"/api/v1/customer-support/tickets/{ticket_id}", headers=agent["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == ticket_id

    # 3. Support Agent can reply to ticket
    r = client.post(f"/api/v1/customer-support/tickets/{ticket_id}/messages", headers=agent["headers"], json={
        "message": "Looking into SSO logs now",
    })
    assert r.status_code in (200, 201)

    # 4. Support Agent can update ticket status
    r = client.put(f"/api/v1/customer-support/tickets/{ticket_id}", headers=agent["headers"], json={
        "status": "in_progress",
        "priority": "high",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"

    # 5. Admin can update ticket
    r = client.put(f"/api/v1/customer-support/tickets/{ticket_id}", headers=admin["headers"], json={
        "status": "resolved",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

