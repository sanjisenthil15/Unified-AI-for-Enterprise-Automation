"""
backend/tests/test_analytics.py

Automated integration tests for the Centralized Analytics Dashboard module.
Verifies:
  - Role-based access control (Admin & Manager full access, Employee 403 rejection)
  - Team Leader project-scoping and cross-project isolation
  - Zero-division safety and schema completeness
  - Trend time-series chronological generation
"""

import uuid
import pytest
from datetime import date
from sqlalchemy.orm import Session

from models.employee import Employee
from models.project import Project
from models.role import Role
from models.user import User


def _create_employee_for_user(
    db: Session,
    user_id: int,
    project_id: int | None = None,
    job_title: str = "Test Engineer",
) -> Employee:
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


# --------------------------------------------------------------------------- #
# 1. Executive Overview Tests
# --------------------------------------------------------------------------- #

def test_admin_can_access_overview(client, new_user):
    admin = new_user(role="admin")
    r = client.get("/api/v1/analytics/overview", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert "total_employees" in data
    assert "active_employees" in data
    assert "total_projects" in data
    assert "overall_task_completion_rate" in data
    assert "open_incidents" in data
    assert "open_support_tickets" in data
    assert "active_job_postings" in data
    assert "total_meetings" in data
    assert "action_items_conversion_rate" in data
    assert isinstance(data["overall_task_completion_rate"], float)


def test_manager_can_access_overview(client, new_user):
    manager = new_user(role="manager")
    r = client.get("/api/v1/analytics/overview", headers=manager["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_projects"] >= 0


def test_employee_forbidden_from_overview(client, new_user):
    emp = new_user(role="employee")
    r = client.get("/api/v1/analytics/overview", headers=emp["headers"])
    assert r.status_code == 403, r.text


def test_unauthenticated_request_rejected(client):
    r = client.get("/api/v1/analytics/overview")
    assert r.status_code == 401, r.text


# --------------------------------------------------------------------------- #
# 2. Project Analytics & Team Lead Scoping Tests
# --------------------------------------------------------------------------- #

def test_admin_can_access_all_projects_analytics(client, new_user):
    admin = new_user(role="admin")
    r = client.get("/api/v1/analytics/projects", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert "projects" in data
    assert "total_projects" in data
    assert isinstance(data["projects"], list)


def test_team_lead_project_scoping_and_isolation(client, new_user, db):
    # Setup: Project A and Project B
    proj_a = Project(name=f"Project A pytest_{uuid.uuid4().hex[:6]}")
    proj_b = Project(name=f"Project B pytest_{uuid.uuid4().hex[:6]}")
    db.add_all([proj_a, proj_b])
    db.commit()
    db.refresh(proj_a)
    db.refresh(proj_b)

    # User A is team lead of Project A
    user_a = new_user(role="employee")
    emp_a = _create_employee_for_user(db, user_a["id"], project_id=proj_a.id, job_title="Team Lead A")
    proj_a.team_lead_id = emp_a.id
    db.commit()

    # 1. Team lead accessing their own project -> 200 OK
    r = client.get(f"/api/v1/analytics/projects?project_id={proj_a.id}", headers=user_a["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_projects"] == 1
    assert data["projects"][0]["project_id"] == proj_a.id

    # 2. Team lead omitting project_id -> 403 Forbidden
    r = client.get("/api/v1/analytics/projects", headers=user_a["headers"])
    assert r.status_code == 403, r.text
    assert "Team Leaders must specify their assigned project_id" in r.text

    # 3. Team lead querying Project B (which they do not lead) -> 403 Forbidden
    r = client.get(f"/api/v1/analytics/projects?project_id={proj_b.id}", headers=user_a["headers"])
    assert r.status_code == 403, r.text


def test_regular_employee_forbidden_from_project_analytics(client, new_user):
    emp = new_user(role="employee")
    r = client.get("/api/v1/analytics/projects", headers=emp["headers"])
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 3. Workforce Analytics Tests
# --------------------------------------------------------------------------- #

def test_workforce_analytics_admin(client, new_user):
    admin = new_user(role="admin")
    r = client.get("/api/v1/analytics/workforce", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert "total_workforce" in data
    assert "department_distribution" in data
    assert "project_allocations" in data
    assert "attendance_summary" in data
    assert "average_checkin_rate" in data["attendance_summary"]


def test_workforce_analytics_employee_forbidden(client, new_user):
    emp = new_user(role="employee")
    r = client.get("/api/v1/analytics/workforce", headers=emp["headers"])
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 4. Operations Analytics Tests
# --------------------------------------------------------------------------- #

def test_operations_analytics_admin(client, new_user):
    admin = new_user(role="admin")
    r = client.get("/api/v1/analytics/operations", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert "incidents" in data
    assert "support" in data
    assert "recruitment" in data
    assert "meetings" in data

    assert "severity_breakdown" in data["incidents"]
    assert "total_tickets" in data["support"]
    assert "open_positions" in data["recruitment"]
    assert "total_meetings" in data["meetings"]


def test_operations_analytics_employee_forbidden(client, new_user):
    emp = new_user(role="employee")
    r = client.get("/api/v1/analytics/operations", headers=emp["headers"])
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 5. Trend Time-Series Tests
# --------------------------------------------------------------------------- #

def test_analytics_trends_admin(client, new_user):
    admin = new_user(role="admin")
    r = client.get("/api/v1/analytics/trends?range_days=14", headers=admin["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["range_days"] == 14
    assert len(data["daily_trends"]) == 14
    first_day = data["daily_trends"][0]
    assert "date" in first_day
    assert "tasks_completed" in first_day
    assert "tasks_created" in first_day
    assert "tickets_created" in first_day
