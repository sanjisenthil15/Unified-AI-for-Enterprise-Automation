"""
test_incident_assignment_workflow.py

Comprehensive tests for AI-assisted team recommendation with Manager-controlled
employee assignment in the Incident Management module:
1. Team listing and dynamic member retrieval.
2. Valid incident assignment using preselected AI-recommended team.
3. Manager overriding the AI-recommended team with another valid team.
4. Validation failure (400 Bad Request) when assigning an employee who does not belong to the selected team.
5. Validation failure (400 Bad Request) when assigning an inactive employee.
6. Missing AI recommendation workflow (manual team selection).
7. Audit log record creation with actor, old assignee, new team, new assignee, override flag, and timestamp.
8. RBAC enforcement: only authorized roles (manager, admin) can assign incidents.
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

from models.audit_log import AuditLog
from models.employee import Employee
from models.incident import Incident, IncidentAITriage, IncidentTimeline
from models.project import Project
from models.user import User

INC_BASE = "/api/v1/incidents"


def test_list_incident_teams_and_members(client, new_user, db):
    manager = new_user("Team List Manager", role="manager")
    employee_user = new_user("Team List Dev", role="employee")

    # Create a test project team and active employee member
    proj = Project(name=f"Workflow Team {uuid.uuid4().hex[:6]}", description="Incident test team")
    db.add(proj)
    db.flush()

    emp = Employee(
        user_id=employee_user["id"],
        employee_code=f"EMP-TL-{uuid.uuid4().hex[:6]}",
        job_title="DevOps Engineer",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
        project_id=proj.id,
    )
    db.add(emp)
    db.commit()

    try:
        # GET /api/v1/incidents/teams
        r_teams = client.get(f"{INC_BASE}/teams", headers=manager["headers"])
        assert r_teams.status_code == 200, r_teams.text
        teams = r_teams.json()
        assert isinstance(teams, list)
        matching_team = next((t for t in teams if t["name"] == proj.name), None)
        assert matching_team is not None
        assert matching_team["team_id"] == proj.id
        assert matching_team["team_type"] == "project"
        assert matching_team["member_count"] >= 1

        # GET /api/v1/incidents/teams/{team_id}/members
        r_members = client.get(f"{INC_BASE}/teams/{matching_team['id']}/members", headers=manager["headers"])
        assert r_members.status_code == 200, r_members.text
        members = r_members.json()
        assert any(m["user_id"] == employee_user["id"] for m in members)

    finally:
        db.delete(emp)
        db.delete(proj)
        db.commit()


def test_assign_incident_ai_recommended_team(client, new_user, db):
    manager = new_user("Assign Manager 1", role="manager")
    dev_user = new_user("Assign Dev 1", role="employee")

    proj = Project(name=f"Infrastructure Platform {uuid.uuid4().hex[:6]}", description="Core Infra")
    db.add(proj)
    db.flush()

    emp = Employee(
        user_id=dev_user["id"],
        employee_code=f"EMP-A1-{uuid.uuid4().hex[:6]}",
        job_title="Site Reliability Engineer",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
        project_id=proj.id,
    )
    db.add(emp)
    db.flush()

    # Create incident
    inc = Incident(
        title="High CPU Load on API Gateway",
        description="Kubernetes ingress controller is throttling requests due to excessive CPU utilization.",
        severity="high",
        affected_system="API Gateway",
        reported_by=manager["id"],
        status="open",
    )
    db.add(inc)
    db.flush()

    # Add AI triage recommending the Infra team
    triage = IncidentAITriage(
        incident_id=inc.id,
        suggested_severity="high",
        suggested_owner=proj.name,
        reasoning="Kubernetes ingress belongs to the infrastructure platform team.",
        confidence=95.0,
        ai_model="gemini-3.6-flash",
    )
    db.add(triage)
    db.commit()

    try:
        # Assign incident to dev_user using the AI-recommended team
        assign_payload = {
            "assigned_to": dev_user["id"],
            "team_id": f"proj_{proj.id}",
            "team_name": proj.name,
            "ai_recommended_team": proj.name,
            "notes": "Assigning to SRE lead per AI triage recommendation.",
        }
        r_assign = client.put(f"{INC_BASE}/{inc.id}/assign", headers=manager["headers"], json=assign_payload)
        assert r_assign.status_code == 200, r_assign.text
        data = r_assign.json()
        assert data["assigned_to"] == dev_user["id"]
        assert data["assignee"]["id"] == dev_user["id"]
        assert data["team_name"] == proj.name

        # Verify timeline entry
        timeline_entry = (
            db.query(IncidentTimeline)
            .filter(IncidentTimeline.incident_id == inc.id, IncidentTimeline.action == "incident_assigned")
            .first()
        )
        assert timeline_entry is not None
        assert "Assigning to SRE lead" in timeline_entry.notes

        # Verify audit log record
        audit_rows = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "incident", AuditLog.entity_id == str(inc.id))
            .all()
        )
        assert len(audit_rows) >= 1
        rich_row = next((r for r in audit_rows if r.after and "is_override" in r.after), None)
        assert rich_row is not None
        assert rich_row.action == "incident.assigned"
        assert rich_row.actor_user_id == manager["id"]
        assert rich_row.after["assigned_to"] == dev_user["id"]
        assert rich_row.after["is_override"] is False
        assert rich_row.after["team_name"] == proj.name

    finally:
        db.query(IncidentTimeline).filter(IncidentTimeline.incident_id == inc.id).delete()
        db.query(IncidentAITriage).filter(IncidentAITriage.incident_id == inc.id).delete()
        db.query(Incident).filter(Incident.id == inc.id).delete()
        db.delete(emp)
        db.delete(proj)
        db.commit()


def test_assign_incident_manager_team_override(client, new_user, db):
    manager = new_user("Assign Manager 2", role="manager")
    dev_user = new_user("Assign Dev 2", role="employee")

    # Team A (suggested by AI) and Team B (chosen by Manager)
    proj_a = Project(name=f"Network Security {uuid.uuid4().hex[:6]}", description="Sec team")
    proj_b = Project(name=f"Application Core {uuid.uuid4().hex[:6]}", description="App team")
    db.add_all([proj_a, proj_b])
    db.flush()

    emp = Employee(
        user_id=dev_user["id"],
        employee_code=f"EMP-A2-{uuid.uuid4().hex[:6]}",
        job_title="Core Developer",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
        project_id=proj_b.id,
    )
    db.add(emp)
    db.flush()

    inc = Incident(
        title="Spike in 401 Unauthorized errors",
        description="Session cookies are being invalidated due to misconfigured expiration logic in app core.",
        severity="medium",
        affected_system="Session Manager",
        reported_by=manager["id"],
        status="open",
    )
    db.add(inc)
    db.flush()

    # AI suggested Network Security
    triage = IncidentAITriage(
        incident_id=inc.id,
        suggested_severity="medium",
        suggested_owner=proj_a.name,
        reasoning="Session errors could indicate a credential stuffing or network authentication issue.",
        confidence=80.0,
        ai_model="gemini-3.6-flash",
    )
    db.add(triage)
    db.commit()

    try:
        # Manager overrides team to Team B (Application Core)
        assign_payload = {
            "assigned_to": dev_user["id"],
            "team_id": f"proj_{proj_b.id}",
            "team_name": proj_b.name,
            "ai_recommended_team": proj_a.name,
            "notes": "Root cause is app logic, overriding AI recommendation to assign to Application Core.",
        }
        r_assign = client.put(f"{INC_BASE}/{inc.id}/assign", headers=manager["headers"], json=assign_payload)
        assert r_assign.status_code == 200, r_assign.text
        data = r_assign.json()
        assert data["assigned_to"] == dev_user["id"]
        assert data["team_name"] == proj_b.name

        # Verify timeline entry notes override
        timeline_entry = (
            db.query(IncidentTimeline)
            .filter(IncidentTimeline.incident_id == inc.id, IncidentTimeline.action == "incident_assigned")
            .first()
        )
        assert timeline_entry is not None
        assert "Overrode AI recommended team" in timeline_entry.notes

        # Verify audit log captures override flag and action name
        audit_rows = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "incident", AuditLog.entity_id == str(inc.id))
            .all()
        )
        assert len(audit_rows) >= 1
        rich_row = next((r for r in audit_rows if r.after and "is_override" in r.after), None)
        assert rich_row is not None
        assert rich_row.action == "incident.assigned_override"
        assert rich_row.after["is_override"] is True
        assert rich_row.after["ai_recommended_team"] == proj_a.name
        assert rich_row.after["team_name"] == proj_b.name

    finally:
        db.query(IncidentTimeline).filter(IncidentTimeline.incident_id == inc.id).delete()
        db.query(IncidentAITriage).filter(IncidentAITriage.incident_id == inc.id).delete()
        db.query(Incident).filter(Incident.id == inc.id).delete()
        db.delete(emp)
        db.delete(proj_a)
        db.delete(proj_b)
        db.commit()


def test_assign_incident_rejects_invalid_team_membership(client, new_user, db):
    manager = new_user("Assign Manager 3", role="manager")
    dev_user = new_user("Assign Dev 3", role="employee")

    proj_actual = Project(name=f"Actual Team {uuid.uuid4().hex[:6]}")
    proj_other = Project(name=f"Other Team {uuid.uuid4().hex[:6]}")
    db.add_all([proj_actual, proj_other])
    db.flush()

    emp = Employee(
        user_id=dev_user["id"],
        employee_code=f"EMP-A3-{uuid.uuid4().hex[:6]}",
        job_title="Backend Engineer",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
        project_id=proj_actual.id,  # Belongs to proj_actual
    )
    db.add(emp)
    db.flush()

    inc = Incident(
        title="Payment webhook failure",
        description="Webhook listener is rejecting incoming payment notifications.",
        severity="high",
        reported_by=manager["id"],
    )
    db.add(inc)
    db.commit()

    try:
        # Attempt to assign dev_user under proj_other (where they are not a member)
        assign_payload = {
            "assigned_to": dev_user["id"],
            "team_id": f"proj_{proj_other.id}",
            "team_name": proj_other.name,
            "notes": "Testing membership mismatch rejection.",
        }
        r = client.put(f"{INC_BASE}/{inc.id}/assign", headers=manager["headers"], json=assign_payload)
        assert r.status_code == 400, r.text
        assert "does not belong to the selected team" in r.json()["detail"]

        # Incident assigned_to remains unassigned
        db.refresh(inc)
        assert inc.assigned_to is None

    finally:
        db.query(Incident).filter(Incident.id == inc.id).delete()
        db.delete(emp)
        db.delete(proj_actual)
        db.delete(proj_other)
        db.commit()


def test_assign_incident_rejects_inactive_employee(client, new_user, db):
    manager = new_user("Assign Manager 4", role="manager")
    inactive_user = new_user("Inactive Dev", role="employee")

    proj = Project(name=f"Team Inactive {uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.flush()

    # Employee record marked as inactive
    emp = Employee(
        user_id=inactive_user["id"],
        employee_code=f"EMP-INACT-{uuid.uuid4().hex[:6]}",
        job_title="Former Engineer",
        hire_date=date(2025, 1, 1),
        employment_type="full_time",
        status="inactive",
        project_id=proj.id,
    )
    db.add(emp)
    db.flush()

    inc = Incident(
        title="Cache node unresponsive",
        description="Redis replica node unresponsive to health check probes.",
        severity="low",
        reported_by=manager["id"],
    )
    db.add(inc)
    db.commit()

    try:
        assign_payload = {
            "assigned_to": inactive_user["id"],
            "team_id": f"proj_{proj.id}",
            "team_name": proj.name,
        }
        r = client.put(f"{INC_BASE}/{inc.id}/assign", headers=manager["headers"], json=assign_payload)
        assert r.status_code == 400, r.text
        assert "inactive employee" in r.json()["detail"].lower()

        db.refresh(inc)
        assert inc.assigned_to is None

    finally:
        db.query(Incident).filter(Incident.id == inc.id).delete()
        db.delete(emp)
        db.delete(proj)
        db.commit()


def test_assign_incident_missing_ai_recommendation(client, new_user, db):
    manager = new_user("Assign Manager 5", role="manager")
    dev_user = new_user("Assign Dev 5", role="employee")

    proj = Project(name=f"Manual Team {uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.flush()

    emp = Employee(
        user_id=dev_user["id"],
        employee_code=f"EMP-M5-{uuid.uuid4().hex[:6]}",
        job_title="Developer",
        hire_date=date(2026, 1, 1),
        status="active",
        project_id=proj.id,
    )
    db.add(emp)
    db.flush()

    inc = Incident(
        title="Manual assignment incident",
        description="No AI triage has been executed for this incident yet.",
        severity="medium",
        reported_by=manager["id"],
    )
    db.add(inc)
    db.commit()

    try:
        # Assign directly without AI recommendation
        assign_payload = {
            "assigned_to": dev_user["id"],
            "team_id": f"proj_{proj.id}",
            "team_name": proj.name,
            "notes": "Direct manager assignment without AI assistance.",
        }
        r = client.put(f"{INC_BASE}/{inc.id}/assign", headers=manager["headers"], json=assign_payload)
        assert r.status_code == 200, r.text
        assert r.json()["assigned_to"] == dev_user["id"]

        audit_rows = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "incident", AuditLog.entity_id == str(inc.id))
            .all()
        )
        assert len(audit_rows) >= 1
        rich_row = next((r for r in audit_rows if r.after and "is_override" in r.after), None)
        assert rich_row is not None
        assert rich_row.action == "incident.assigned"
        assert rich_row.after["is_override"] is False

    finally:
        db.query(IncidentTimeline).filter(IncidentTimeline.incident_id == inc.id).delete()
        db.query(Incident).filter(Incident.id == inc.id).delete()
        db.delete(emp)
        db.delete(proj)
        db.commit()


def test_assign_incident_rbac_permissions(client, new_user, db):
    admin = new_user("Assign Admin", role="admin")
    manager = new_user("Assign Manager RBAC", role="manager")
    employee = new_user("Assign Unauthorized Employee", role="employee")

    inc = Incident(
        title="RBAC Check Incident",
        description="Checking RBAC permissions for assigning incidents.",
        severity="low",
        reported_by=admin["id"],
    )
    db.add(inc)
    db.commit()

    try:
        # Employee cannot assign incidents (403 Forbidden)
        r_emp = client.put(f"{INC_BASE}/{inc.id}/assign", headers=employee["headers"], json={"assigned_to": admin["id"]})
        assert r_emp.status_code == 403

        # Manager is authorized to access assign endpoint
        r_mgr = client.put(f"{INC_BASE}/{inc.id}/assign", headers=manager["headers"], json={"assigned_to": 999999})
        assert r_mgr.status_code == 404  # Passes RBAC, target user not found

        # Admin is authorized to access assign endpoint
        r_adm = client.put(f"{INC_BASE}/{inc.id}/assign", headers=admin["headers"], json={"assigned_to": 999999})
        assert r_adm.status_code == 404  # Passes RBAC, target user not found

    finally:
        db.query(Incident).filter(Incident.id == inc.id).delete()
        db.commit()
