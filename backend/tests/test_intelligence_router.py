"""
backend/tests/test_intelligence_router.py

Comprehensive integration test suite for Phase 3.3: Intelligence API Endpoints & RBAC Integration.
Verifies:
  1. Authentication: Missing or invalid token returns 401.
  2. Admin Access: Full organization-wide intelligence access and cache refresh (200).
  3. Manager Access: Full organization-wide intelligence access (200), forbidden from system administration (403).
  4. Team Leader Scoping: Assigned project returns 200, cross-project access returns 403,
     missing project_id returns 403, cross-project refresh returns 403.
  5. Employee Access: All intelligence endpoints return 403.
  6. Operational Safety: Gemini fallback resilience, refresh throttling (429),
     invalid project 404 handling, and strict PII exclusion.
"""

from datetime import date
import uuid
import pytest
from sqlalchemy.orm import Session

from models.employee import Employee
from models.project import Project
from modules.intelligence.cache import intelligence_cache


def _create_employee_for_user(
    db: Session,
    user_id: int,
    project_id: int | None = None,
    job_title: str = "Test Engineer",
) -> Employee:
    """Helper to attach an Employee record to a User in the PostgreSQL test database."""
    code = f"EMP-{uuid.uuid4().hex[:6].upper()}"
    emp = Employee(
        user_id=user_id,
        employee_code=code,
        job_title=job_title,
        hire_date=date.today(),
        status="active",
        project_id=project_id,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


from unittest.mock import patch
from modules.intelligence.ai_client import AIQuotaError


@pytest.fixture(autouse=True)
def mock_gemini_in_router_tests():
    """Mocks Gemini API calls across all router tests so zero external API calls or quota are consumed."""
    with patch("modules.intelligence.service.GeminiClient.generate_structured") as mock_gen:
        mock_gen.side_effect = AIQuotaError("Mocked Gemini Quota for Test")
        yield mock_gen


# --------------------------------------------------------------------------- #
# 1. Authentication Tests
# --------------------------------------------------------------------------- #

def test_missing_token_returns_401(client):
    """Verifies that all intelligence endpoints reject requests without a Bearer token."""
    intelligence_cache.clear()

    r1 = client.get("/api/v1/intelligence/executive-summary")
    assert r1.status_code == 401, r1.text

    r2 = client.get("/api/v1/intelligence/project-risks")
    assert r2.status_code == 401, r2.text

    r3 = client.get("/api/v1/intelligence/sprint-delays")
    assert r3.status_code == 401, r3.text

    r4 = client.get("/api/v1/intelligence/workload-bottlenecks")
    assert r4.status_code == 401, r4.text

    r5 = client.get("/api/v1/intelligence/operations-insights")
    assert r5.status_code == 401, r5.text

    r6 = client.post("/api/v1/intelligence/refresh")
    assert r6.status_code == 401, r6.text


def test_invalid_token_returns_401(client):
    """Verifies that malformed or forged tokens are rejected with 401."""
    headers = {"Authorization": "Bearer invalid.mock.jwt.token"}
    r = client.get("/api/v1/intelligence/executive-summary", headers=headers)
    assert r.status_code == 401, r.text


# --------------------------------------------------------------------------- #
# 2. Admin Access Tests
# --------------------------------------------------------------------------- #

def test_admin_organization_wide_endpoints_return_200(client, new_user):
    """Verifies Admin has full organization-wide access across all intelligence endpoints."""
    admin = new_user(role="admin")
    intelligence_cache.clear()

    # 1. Executive Summary
    r_exec = client.get("/api/v1/intelligence/executive-summary", headers=admin["headers"])
    assert r_exec.status_code == 200, r_exec.text
    data_exec = r_exec.json()
    assert "overall_status" in data_exec
    assert "recommendations" in data_exec
    assert "metadata" in data_exec

    # 2. Project Risks (All Projects)
    r_risks = client.get("/api/v1/intelligence/project-risks", headers=admin["headers"])
    assert r_risks.status_code == 200, r_risks.text
    data_risks = r_risks.json()
    assert "projects" in data_risks

    # 3. Sprint Delays
    r_sprints = client.get("/api/v1/intelligence/sprint-delays", headers=admin["headers"])
    assert r_sprints.status_code == 200, r_sprints.text
    data_sprints = r_sprints.json()
    assert "sprints" in data_sprints

    # 4. Workload Bottlenecks
    r_workload = client.get("/api/v1/intelligence/workload-bottlenecks", headers=admin["headers"])
    assert r_workload.status_code == 200, r_workload.text
    data_workload = r_workload.json()
    assert "bottlenecks" in data_workload

    # 5. Operations Insights
    r_ops = client.get("/api/v1/intelligence/operations-insights", headers=admin["headers"])
    assert r_ops.status_code == 200, r_ops.text
    data_ops = r_ops.json()
    assert "support_insights" in data_ops
    assert "incident_insights" in data_ops


def test_admin_refresh_is_authorized(client, new_user):
    """Verifies Admin is authorized to trigger cache invalidation."""
    admin = new_user(role="admin")
    intelligence_cache.clear()

    r = client.post("/api/v1/intelligence/refresh", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "refreshed"
    assert data["scope"] == "org"


# --------------------------------------------------------------------------- #
def _cleanup_test_managers():
    from config.database import engine
    from sqlalchemy import text
    with engine.begin() as conn:
        mgr_user_ids = [
            r[0] for r in conn.execute(
                text("SELECT id FROM users WHERE email LIKE '%pytest%' AND role_id IN (SELECT id FROM roles WHERE name = 'manager')")
            )
        ]
        if not mgr_user_ids:
            return
        conn.execute(text("DELETE FROM manager_chat_threads WHERE manager_user_id = ANY(:ids) OR employee_id IN (SELECT id FROM employees WHERE user_id = ANY(:ids))"), {"ids": mgr_user_ids})
        conn.execute(text("DELETE FROM attendance_records WHERE employee_id IN (SELECT id FROM employees WHERE user_id = ANY(:ids))"), {"ids": mgr_user_ids})
        conn.execute(text("DELETE FROM sprints WHERE created_by IN (SELECT id FROM employees WHERE user_id = ANY(:ids))"), {"ids": mgr_user_ids})
        conn.execute(text("DELETE FROM notifications WHERE user_id = ANY(:ids)"), {"ids": mgr_user_ids})
        conn.execute(text("DELETE FROM employees WHERE user_id = ANY(:ids)"), {"ids": mgr_user_ids})
        conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": mgr_user_ids})


# --------------------------------------------------------------------------- #
# 3. Manager Access Tests
# --------------------------------------------------------------------------- #

def test_manager_organization_wide_intelligence_and_restrictions(client, new_user):
    """Verifies Manager has full organization-wide intelligence visibility across all 3 projects,
    while system administration remains strictly forbidden (admin/hr only)."""
    _cleanup_test_managers()
    manager = new_user(role="manager")
    intelligence_cache.clear()

    # 1. Access all 5 intelligence endpoints
    r_exec = client.get("/api/v1/intelligence/executive-summary", headers=manager["headers"])
    assert r_exec.status_code == 200, r_exec.text

    r_risks = client.get("/api/v1/intelligence/project-risks", headers=manager["headers"])
    assert r_risks.status_code == 200, r_risks.text

    r_sprints = client.get("/api/v1/intelligence/sprint-delays", headers=manager["headers"])
    assert r_sprints.status_code == 200, r_sprints.text

    r_workload = client.get("/api/v1/intelligence/workload-bottlenecks", headers=manager["headers"])
    assert r_workload.status_code == 200, r_workload.text

    r_ops = client.get("/api/v1/intelligence/operations-insights", headers=manager["headers"])
    assert r_ops.status_code == 200, r_ops.text

    # 2. Manager can trigger refresh
    r_ref = client.post("/api/v1/intelligence/refresh", headers=manager["headers"])
    assert r_ref.status_code == 200, r_ref.text

    # 3. Manager cannot perform Admin-only employee onboarding (403)
    payload = {
        "user_id": 9999,
        "employee_code": "EMP-FAIL",
        "job_title": "Illegal",
        "hire_date": "2026-10-31",
    }
    r_admin_action = client.post("/api/v1/employee-management/employees", json=payload, headers=manager["headers"])
    assert r_admin_action.status_code == 403, r_admin_action.text


# --------------------------------------------------------------------------- #
# 4. Team Leader Scoping & Project Isolation Tests
# --------------------------------------------------------------------------- #

def test_team_leader_assigned_project_returns_200(client, new_user, db):
    """Verifies Team Leader can access intelligence for their assigned project."""
    intelligence_cache.clear()

    # Create Project A
    proj_a = Project(name=f"Project A pytest_{uuid.uuid4().hex[:6]}")
    db.add(proj_a)
    db.commit()
    db.refresh(proj_a)

    # Designate User A as Team Lead of Project A
    user_a = new_user(role="employee")
    emp_a = _create_employee_for_user(db, user_a["id"], project_id=proj_a.id, job_title="Team Lead A")
    proj_a.team_lead_id = emp_a.id
    db.commit()

    # Team Lead A accesses Project A
    r_risks = client.get(f"/api/v1/intelligence/project-risks?project_id={proj_a.id}", headers=user_a["headers"])
    assert r_risks.status_code == 200, r_risks.text

    r_sprints = client.get(f"/api/v1/intelligence/sprint-delays?project_id={proj_a.id}", headers=user_a["headers"])
    assert r_sprints.status_code == 200, r_sprints.text

    r_workload = client.get(f"/api/v1/intelligence/workload-bottlenecks?project_id={proj_a.id}", headers=user_a["headers"])
    assert r_workload.status_code == 200, r_workload.text


def test_team_leader_other_project_returns_403(client, new_user, db):
    """Verifies Team Leader receives 403 when attempting to access another project's intelligence."""
    intelligence_cache.clear()

    # Create Project A and Project B
    proj_a = Project(name=f"Project A pytest_{uuid.uuid4().hex[:6]}")
    proj_b = Project(name=f"Project B pytest_{uuid.uuid4().hex[:6]}")
    db.add_all([proj_a, proj_b])
    db.commit()
    db.refresh(proj_a)
    db.refresh(proj_b)

    # User A is Lead of Project A
    user_a = new_user(role="employee")
    emp_a = _create_employee_for_user(db, user_a["id"], project_id=proj_a.id, job_title="Team Lead A")
    proj_a.team_lead_id = emp_a.id
    db.commit()

    # Lead A attempts to access Project B
    r_risks = client.get(f"/api/v1/intelligence/project-risks?project_id={proj_b.id}", headers=user_a["headers"])
    assert r_risks.status_code == 403, r_risks.text
    assert "not the team lead" in r_risks.json()["detail"].lower()

    r_sprints = client.get(f"/api/v1/intelligence/sprint-delays?project_id={proj_b.id}", headers=user_a["headers"])
    assert r_sprints.status_code == 403, r_sprints.text

    r_workload = client.get(f"/api/v1/intelligence/workload-bottlenecks?project_id={proj_b.id}", headers=user_a["headers"])
    assert r_workload.status_code == 403, r_workload.text


def test_team_leader_missing_project_id_returns_403(client, new_user, db):
    """Verifies Team Leader cannot access organization-wide datasets without specifying their project."""
    intelligence_cache.clear()

    proj = Project(name=f"Project pytest_{uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    user_lead = new_user(role="employee")
    emp_lead = _create_employee_for_user(db, user_lead["id"], project_id=proj.id, job_title="Lead")
    proj.team_lead_id = emp_lead.id
    db.commit()

    # Missing project_id query parameter
    r1 = client.get("/api/v1/intelligence/project-risks", headers=user_lead["headers"])
    assert r1.status_code == 403, r1.text

    r2 = client.get("/api/v1/intelligence/sprint-delays", headers=user_lead["headers"])
    assert r2.status_code == 403, r2.text

    r3 = client.get("/api/v1/intelligence/workload-bottlenecks", headers=user_lead["headers"])
    assert r3.status_code == 403, r3.text

    # Org-only endpoints forbidden for Team Leader
    r_exec = client.get("/api/v1/intelligence/executive-summary", headers=user_lead["headers"])
    assert r_exec.status_code == 403, r_exec.text

    r_ops = client.get("/api/v1/intelligence/operations-insights", headers=user_lead["headers"])
    assert r_ops.status_code == 403, r_ops.text


def test_team_leader_refresh_security_and_isolation(client, new_user, db):
    """Verifies Team Leader can refresh only their project scope, not other projects or org-wide."""
    intelligence_cache.clear()

    proj_a = Project(name=f"Project A pytest_{uuid.uuid4().hex[:6]}")
    proj_b = Project(name=f"Project B pytest_{uuid.uuid4().hex[:6]}")
    db.add_all([proj_a, proj_b])
    db.commit()
    db.refresh(proj_a)
    db.refresh(proj_b)

    user_a = new_user(role="employee")
    emp_a = _create_employee_for_user(db, user_a["id"], project_id=proj_a.id, job_title="Lead A")
    proj_a.team_lead_id = emp_a.id
    db.commit()

    # 1. Lead A attempts org-wide refresh -> 403
    r_org = client.post("/api/v1/intelligence/refresh", headers=user_a["headers"])
    assert r_org.status_code == 403, r_org.text

    # 2. Lead A attempts to refresh Project B -> 403
    r_other = client.post(f"/api/v1/intelligence/refresh?project_id={proj_b.id}", headers=user_a["headers"])
    assert r_other.status_code == 403, r_other.text

    # 3. Lead A refreshes Project A -> 200
    r_own = client.post(f"/api/v1/intelligence/refresh?project_id={proj_a.id}", headers=user_a["headers"])
    assert r_own.status_code == 200, r_own.text
    assert r_own.json()["status"] == "refreshed"
    assert r_own.json()["project_id"] == proj_a.id


# --------------------------------------------------------------------------- #
# 5. Regular Employee Access Rejection Tests
# --------------------------------------------------------------------------- #

def test_employee_forbidden_from_all_intelligence_endpoints(client, new_user, db):
    """Verifies regular Employees (non-leads) are rejected with 403 on all intelligence endpoints."""
    proj = Project(name=f"Project pytest_{uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    emp_user = new_user(role="employee")
    _create_employee_for_user(db, emp_user["id"], project_id=proj.id, job_title="Engineer")

    endpoints = [
        "/api/v1/intelligence/executive-summary",
        "/api/v1/intelligence/project-risks",
        f"/api/v1/intelligence/project-risks?project_id={proj.id}",
        "/api/v1/intelligence/sprint-delays",
        f"/api/v1/intelligence/sprint-delays?project_id={proj.id}",
        "/api/v1/intelligence/workload-bottlenecks",
        f"/api/v1/intelligence/workload-bottlenecks?project_id={proj.id}",
        "/api/v1/intelligence/operations-insights",
    ]

    for ep in endpoints:
        r = client.get(ep, headers=emp_user["headers"])
        assert r.status_code == 403, f"Endpoint {ep} did not reject regular employee: {r.status_code}"

    r_post = client.post("/api/v1/intelligence/refresh", headers=emp_user["headers"])
    assert r_post.status_code == 403, r_post.text


# --------------------------------------------------------------------------- #
# 6. Operational Safety: Throttling, Invalid Project, and PII Exclusion
# --------------------------------------------------------------------------- #

def test_refresh_throttling_cooldown(client, new_user):
    """Verifies that invoking refresh within the 10-second cooldown returns HTTP 429."""
    admin = new_user(role="admin")
    intelligence_cache.clear()

    # First refresh: 200 OK
    r1 = client.post("/api/v1/intelligence/refresh", headers=admin["headers"])
    assert r1.status_code == 200, r1.text

    # Immediate second refresh: 429 Too Many Requests
    r2 = client.post("/api/v1/intelligence/refresh", headers=admin["headers"])
    assert r2.status_code == 429, r2.text
    assert "cooldown" in r2.json()["detail"].lower()


def test_invalid_project_id_returns_404(client, new_user):
    """Verifies that requesting intelligence for a non-existent project returns 404."""
    admin = new_user(role="admin")
    r = client.get("/api/v1/intelligence/project-risks?project_id=999999", headers=admin["headers"])
    assert r.status_code == 404, r.text


def test_intelligence_responses_contain_no_confidential_pii(client, new_user):
    """Verifies that generated responses do not leak raw emails, phone numbers, or passwords."""
    admin = new_user(role="admin")
    intelligence_cache.clear()

    r = client.get("/api/v1/intelligence/executive-summary", headers=admin["headers"])
    assert r.status_code == 200, r.text
    content = r.text
    assert "@enterprise.com" not in content
    assert "password" not in content
    assert "hashed_password" not in content
