"""
backend/tests/test_demo_organization.py

Verification tests for Phase 1 Demo Organization setup:
1. Projects and Manager relationship
2. Team Leader preservation
3. Support Agent, Recruiter, and Viewer accounts
4. Idempotency on rerun
"""

import pytest
from sqlalchemy.orm import Session

from models.employee import Employee
from models.project import Project
from models.role import Role
from models.user import User
from scripts.setup_demo_organization import run_setup


def test_demo_organization_accounts_and_relationships(db: Session):
    # Run setup
    result = run_setup()
    assert result is not None

    # Verify main projects
    projects = db.query(Project).filter(Project.name.in_([
        "Customer Support Platform",
        "Meeting Intelligence",
        "Recruitment AI",
    ])).all()
    assert len(projects) == 3

    # Verify Manager
    manager_user = db.query(User).filter(User.email == "elena.rostova@employee.demo").first()
    assert manager_user is not None
    assert manager_user.role.name == "manager"
    assert manager_user.is_active is True
    assert manager_user.must_change_password is True

    # Verify same manager is assigned to all three projects
    for p in projects:
        assert p.manager_user_id == manager_user.id

    # Verify Team Leaders
    csp = next(p for p in projects if p.name == "Customer Support Platform")
    lead_csp = db.query(Employee).filter(Employee.id == csp.team_lead_id).first()
    assert lead_csp is not None
    assert "sarathi" in lead_csp.user.email.lower()

    mi = next(p for p in projects if p.name == "Meeting Intelligence")
    lead_mi = db.query(Employee).filter(Employee.id == mi.team_lead_id).first()
    assert lead_mi is not None
    assert "srinithi" in lead_mi.user.email.lower()

    rai = next(p for p in projects if p.name == "Recruitment AI")
    lead_rai = db.query(Employee).filter(Employee.id == rai.team_lead_id).first()
    assert lead_rai is not None
    assert "vishwa" in lead_rai.user.email.lower()

    # Verify Support Agent
    sa = db.query(User).filter(User.email == "aiden.cross@employee.demo").first()
    assert sa is not None
    assert sa.role.name == "support_agent"

    # Verify Recruiter
    recruiter = db.query(User).filter(User.email == "chloe.bennett@employee.demo").first()
    assert recruiter is not None
    assert recruiter.role.name == "recruiter"

    # Verify Viewer
    viewer = db.query(User).filter(User.email == "julian.hayes@employee.demo").first()
    assert viewer is not None
    assert viewer.role.name == "viewer"


def test_demo_organization_setup_is_idempotent(db: Session):
    count_users_before = db.query(User).filter(User.email.in_([
        "elena.rostova@employee.demo",
        "aiden.cross@employee.demo",
        "chloe.bennett@employee.demo",
        "julian.hayes@employee.demo",
    ])).count()
    assert count_users_before == 4

    # Run setup a second time
    result = run_setup()
    assert result is not None

    count_users_after = db.query(User).filter(User.email.in_([
        "elena.rostova@employee.demo",
        "aiden.cross@employee.demo",
        "chloe.bennett@employee.demo",
        "julian.hayes@employee.demo",
    ])).count()
    assert count_users_after == 4

