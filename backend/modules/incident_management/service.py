"""
modules/incident_management/service.py

Business logic for the Incident Management module.

Functions:
    get_incident_or_404         — shared fetch helper
    create_incident             — POST /incidents
    list_incidents              — GET  /incidents (with filters + pagination)
    get_incident                — GET  /incidents/{id}
    update_incident             — PUT  /incidents/{id}
    update_incident_status      — PUT  /incidents/{id}/status
    assign_incident             — PUT  /incidents/{id}/assign
    resolve_incident            — PUT  /incidents/{id}/resolve
    close_incident              — PUT  /incidents/{id}/close
    delete_incident             — DELETE /incidents/{id}
    get_incident_timeline       — GET  /incidents/{id}/timeline
    run_ai_triage               — POST /incidents/{id}/triage
    get_latest_triage           — GET  /incidents/{id}/triage
    get_incident_stats          — GET  /incidents/statistics

Timeline helper:
    _add_timeline               — internal, records every audit event
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple, Union

from fastapi import HTTPException, status
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from config.settings import settings
from core import audit
from models.department import Department
from models.employee import Employee
from models.incident import Incident, IncidentAITriage, IncidentTimeline
from models.project import Project
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.user import User
from modules.incident_management.schemas import (
    AITriageResponse,
    IncidentResponse,
    IncidentTeamMember,
    IncidentTeamResponse,
)

# Import google-genai at module level. Using try/except so the server
# starts even if the package is missing (run_ai_triage will 503 instead of crash).
try:
    from google import genai as _genai
except ImportError:
    _genai = None  # type: ignore[assignment]


# ------------------------------------------------------------------ #
# Valid status transitions
# ------------------------------------------------------------------ #

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open":          {"investigating", "resolved", "closed"},
    "investigating": {"resolved", "closed", "open"},
    "resolved":      {"closed", "open"},          # allow reopen
    "closed":        {"open"},                     # allow reopen
}


# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# Team and Assignee Resolution Helpers
# ------------------------------------------------------------------ #

def _parse_team_identifier(team_id: Union[str, int]) -> Tuple[str, int]:
    """Returns (team_type, numeric_id) where team_type is 'project' or 'department'."""
    if isinstance(team_id, int):
        return ("project", team_id)
    s = str(team_id).strip()
    if s.startswith("proj_") or s.startswith("project_") or s.startswith("proj-"):
        parts = s.split("_", 1) if "_" in s else s.split("-", 1)
        return ("project", int(parts[1]))
    if s.startswith("dept_") or s.startswith("department_") or s.startswith("dept-"):
        parts = s.split("_", 1) if "_" in s else s.split("-", 1)
        return ("department", int(parts[1]))
    if s.isdigit():
        return ("project", int(s))
    return ("unknown", 0)


def _get_user_team_name(db: Session, user_id: Optional[int]) -> Optional[str]:
    """Return the project or department name of an active employee user."""
    if not user_id:
        return None
    emp = db.query(Employee).filter(
        Employee.user_id == user_id,
        Employee.deleted_at.is_(None),
    ).first()
    if not emp:
        return None
    if emp.project_id:
        proj = db.query(Project).filter(Project.id == emp.project_id).first()
        if proj:
            return proj.name
    if emp.department_id:
        dept = db.query(Department).filter(Department.id == emp.department_id).first()
        if dept:
            return dept.name
    return None


def _teams_match(ai_team: Optional[str], selected_team: Optional[str]) -> bool:
    """Case-insensitive and clean match between AI recommended team and selected team."""
    if not ai_team or not selected_team:
        return False
    a = ai_team.strip().lower()
    b = selected_team.strip().lower()
    if a == b:
        return True
    clean_a = re.sub(r"\b(team|squad|platform|group|department)\b", "", a).strip()
    clean_b = re.sub(r"\b(team|squad|platform|group|department)\b", "", b).strip()
    if clean_a and clean_b and (clean_a in clean_b or clean_b in clean_a):
        return True
    return False


def list_incident_teams(db: Session) -> List[IncidentTeamResponse]:
    """List available project and department teams with their active employee members."""
    teams: List[IncidentTeamResponse] = []

    # 1. Projects
    projects = (
        db.query(Project)
        .filter(Project.status != "archived")
        .order_by(Project.name.asc())
        .all()
    )
    for p in projects:
        active_emps = (
            db.query(Employee)
            .join(User, User.id == Employee.user_id)
            .filter(
                Employee.project_id == p.id,
                Employee.status == "active",
                Employee.deleted_at.is_(None),
                User.is_active == True,
                User.deleted_at.is_(None),
            )
            .order_by(User.full_name.asc())
            .all()
        )
        if not active_emps and p.id not in (2, 3, 4):
            continue
        members = [
            IncidentTeamMember(
                user_id=e.user.id,
                employee_id=e.id,
                full_name=e.user.full_name,
                email=e.user.email,
                job_title=e.job_title,
                role=e.user.role.name if (e.user and e.user.role) else "employee",
                status=e.status,
            )
            for e in active_emps
            if e.user
        ]
        teams.append(
            IncidentTeamResponse(
                id=f"proj_{p.id}",
                team_id=p.id,
                team_type="project",
                name=p.name,
                description=p.description,
                member_count=len(members),
                members=members,
            )
        )

    # 2. Departments with active members
    departments = db.query(Department).order_by(Department.name.asc()).all()
    for d in departments:
        active_emps = (
            db.query(Employee)
            .join(User, User.id == Employee.user_id)
            .filter(
                Employee.department_id == d.id,
                Employee.status == "active",
                Employee.deleted_at.is_(None),
                User.is_active == True,
                User.deleted_at.is_(None),
            )
            .order_by(User.full_name.asc())
            .all()
        )
        if active_emps:
            members = [
                IncidentTeamMember(
                    user_id=e.user.id,
                    employee_id=e.id,
                    full_name=e.user.full_name,
                    email=e.user.email,
                    job_title=e.job_title,
                    role=e.user.role.name if (e.user and e.user.role) else "employee",
                    status=e.status,
                )
                for e in active_emps
                if e.user
            ]
            teams.append(
                IncidentTeamResponse(
                    id=f"dept_{d.id}",
                    team_id=d.id,
                    team_type="department",
                    name=d.name,
                    description=d.description,
                    member_count=len(members),
                    members=members,
                )
            )

    return teams


def list_team_members(db: Session, team_identifier: Union[str, int]) -> List[IncidentTeamMember]:
    """Dynamically return active employees belonging to the specified team."""
    team_type, num_id = _parse_team_identifier(team_identifier)
    q = (
        db.query(Employee)
        .join(User, User.id == Employee.user_id)
        .filter(
            Employee.status == "active",
            Employee.deleted_at.is_(None),
            User.is_active == True,
            User.deleted_at.is_(None),
        )
    )
    if team_type == "project":
        q = q.filter(Employee.project_id == num_id)
    elif team_type == "department":
        q = q.filter(Employee.department_id == num_id)
    else:
        s_id = str(team_identifier).strip().lower()
        proj = db.query(Project).filter(sqlfunc.lower(Project.name) == s_id).first()
        if proj:
            q = q.filter(Employee.project_id == proj.id)
        else:
            dept = db.query(Department).filter(sqlfunc.lower(Department.name) == s_id).first()
            if dept:
                q = q.filter(Employee.department_id == dept.id)
            else:
                return []

    active_emps = q.order_by(User.full_name.asc()).all()
    return [
        IncidentTeamMember(
            user_id=e.user.id,
            employee_id=e.id,
            full_name=e.user.full_name,
            email=e.user.email,
            job_title=e.job_title,
            role=e.user.role.name if (e.user and e.user.role) else "employee",
            status=e.status,
        )
        for e in active_emps
        if e.user
    ]

# Shared fetch helper
# ------------------------------------------------------------------ #

def get_incident_or_404(db: Session, incident_id: int) -> Incident:
    """Return the Incident or raise HTTP 404."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident id={incident_id} not found.",
        )
    return incident


# ------------------------------------------------------------------ #
# Timeline helper
# ------------------------------------------------------------------ #

def _add_timeline(
    db: Session,
    incident_id: int,
    action: str,
    actor_id: Optional[int],   # None = AI action
    notes: Optional[str] = None,
) -> IncidentTimeline:
    entry = IncidentTimeline(
        incident_id=incident_id,
        actor_id=actor_id,
        action=action,
        notes=notes,
    )
    db.add(entry)
    # Caller is responsible for db.commit()
    return entry


# ------------------------------------------------------------------ #
# Create
# ------------------------------------------------------------------ #

def create_incident(db: Session, payload, reporter_id: int) -> Incident:
    """Create a new incident and record the creation in timeline."""
    incident = Incident(
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        affected_system=payload.affected_system,
        status="open",
        reported_by=reporter_id,
    )
    db.add(incident)
    db.flush()   # get incident.id before timeline insert

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_created",
        actor_id=reporter_id,
        notes=f"Incident created with severity '{payload.severity}'.",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# List (with filters and simple pagination)
# ------------------------------------------------------------------ #

def list_incidents(
    db: Session,
    status_filter: Optional[str]  = None,
    severity_filter: Optional[str] = None,
    assigned_to: Optional[int]    = None,
    reported_by: Optional[int]    = None,
    affected_system: Optional[str] = None,
    search: Optional[str]         = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Incident]:
    q = db.query(Incident)

    if status_filter:
        q = q.filter(Incident.status == status_filter)
    if severity_filter:
        q = q.filter(Incident.severity == severity_filter)
    if assigned_to is not None:
        q = q.filter(Incident.assigned_to == assigned_to)
    if reported_by is not None:
        q = q.filter(Incident.reported_by == reported_by)
    if affected_system:
        q = q.filter(Incident.affected_system.ilike(f"%{affected_system}%"))
    if search:
        term = f"%{search}%"
        q = q.filter(
            Incident.title.ilike(term) | Incident.description.ilike(term)
        )

    return (
        q.order_by(Incident.created_at.desc())
         .offset(skip)
         .limit(limit)
         .all()
    )


# ------------------------------------------------------------------ #
# Get single
# ------------------------------------------------------------------ #

def get_incident(db: Session, incident_id: int) -> IncidentResponse:
    incident = get_incident_or_404(db, incident_id)
    resp = IncidentResponse.model_validate(incident)
    if incident.assigned_to:
        t_name = _get_user_team_name(db, incident.assigned_to)
        resp.team_name = t_name
        if resp.assignee:
            resp.assignee.team_name = t_name
            if incident.assignee and incident.assignee.role:
                resp.assignee.role = incident.assignee.role.name
    latest_triage = (
        db.query(IncidentAITriage)
        .filter(IncidentAITriage.incident_id == incident.id)
        .order_by(IncidentAITriage.generated_at.desc())
        .first()
    )
    if latest_triage:
        resp.ai_triage = AITriageResponse.model_validate(latest_triage)
    return resp


# ------------------------------------------------------------------ #
# Update (general field edit)
# ------------------------------------------------------------------ #

def update_incident(db: Session, incident_id: int, payload, actor_id: int) -> Incident:
    incident = get_incident_or_404(db, incident_id)
    changes  = []

    if payload.title is not None and payload.title != incident.title:
        changes.append(f"title changed")
        incident.title = payload.title

    if payload.description is not None and payload.description != incident.description:
        changes.append("description updated")
        incident.description = payload.description

    if payload.severity is not None and payload.severity != incident.severity:
        changes.append(f"severity changed from '{incident.severity}' to '{payload.severity}'")
        incident.severity = payload.severity

    if payload.affected_system is not None and payload.affected_system != incident.affected_system:
        changes.append(f"affected_system updated to '{payload.affected_system}'")
        incident.affected_system = payload.affected_system

    if payload.root_cause is not None and payload.root_cause != incident.root_cause:
        changes.append("root_cause updated")
        incident.root_cause = payload.root_cause

    if changes:
        _add_timeline(
            db,
            incident_id=incident.id,
            action="incident_updated",
            actor_id=actor_id,
            notes="; ".join(changes),
        )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Status update
# ------------------------------------------------------------------ #

def update_incident_status(
    db: Session, incident_id: int, new_status: str,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)
    old_status = incident.status

    if new_status == old_status:
        return incident   # no-op

    allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition: '{old_status}' → '{new_status}'. "
                f"Allowed from '{old_status}': {sorted(allowed)}."
            ),
        )

    incident.status = new_status
    _add_timeline(
        db,
        incident_id=incident.id,
        action="status_changed",
        actor_id=actor_id,
        notes=notes or f"Status changed from '{old_status}' to '{new_status}'.",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Assign
# ------------------------------------------------------------------ #

def assign_incident(
    db: Session,
    incident_id: int,
    assigned_to_user_id: int,
    actor_id: int,
    notes: Optional[str] = None,
    team_id: Optional[Union[str, int]] = None,
    team_name: Optional[str] = None,
    ai_recommended_team: Optional[str] = None,
    deadline: Optional[Union[date, str]] = None,
) -> IncidentResponse:
    incident = get_incident_or_404(db, incident_id)

    # 1. Validate target user exists and is active
    target_user = db.query(User).filter(
        User.id == assigned_to_user_id,
        User.deleted_at.is_(None),
        User.is_active == True,
    ).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User id={assigned_to_user_id} not found or inactive.",
        )

    # 2. Validate user is an active employee
    target_employee = db.query(Employee).filter(
        Employee.user_id == target_user.id,
        Employee.deleted_at.is_(None),
    ).first()
    if not target_employee or target_employee.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot assign incident to an inactive employee.",
        )

    # 3. Validate team membership if team_id provided
    if team_id is not None:
        team_type, num_id = _parse_team_identifier(team_id)
        if team_type == "project":
            if target_employee.project_id != num_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Employee '{target_user.full_name}' does not belong to the selected team.",
                )
            if not team_name:
                p = db.query(Project).filter(Project.id == num_id).first()
                if p:
                    team_name = p.name
        elif team_type == "department":
            if target_employee.department_id != num_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Employee '{target_user.full_name}' does not belong to the selected team.",
                )
            if not team_name:
                d = db.query(Department).filter(Department.id == num_id).first()
                if d:
                    team_name = d.name

    if not team_name:
        team_name = _get_user_team_name(db, target_user.id) or "Unassigned Team"

    # 4. Determine AI recommendation and override status
    latest_triage = (
        db.query(IncidentAITriage)
        .filter(IncidentAITriage.incident_id == incident.id)
        .order_by(IncidentAITriage.generated_at.desc())
        .first()
    )
    ai_team = latest_triage.suggested_owner if latest_triage else ai_recommended_team
    is_override = False
    if ai_team and team_name:
        if not _teams_match(ai_team, team_name):
            is_override = True

    # 5. Capture prior state for audit log
    old_assignee_id = incident.assigned_to
    old_user = db.query(User).filter(User.id == old_assignee_id).first() if old_assignee_id else None
    old_team_name = _get_user_team_name(db, old_assignee_id) if old_assignee_id else None
    actor_user = db.query(User).filter(User.id == actor_id).first()

    # 6. Apply assignment
    incident.assigned_to = assigned_to_user_id

    # 7. Parse deadline and create/update Sprint Task in "To Do"
    parsed_deadline: Optional[date] = None
    if deadline:
        if isinstance(deadline, str) and deadline.strip():
            try:
                parsed_deadline = datetime.strptime(deadline[:10], "%Y-%m-%d").date()
            except Exception:
                parsed_deadline = None
        elif isinstance(deadline, date):
            parsed_deadline = deadline

    target_project_id = target_employee.project_id
    if not target_project_id and team_id is not None:
        team_type, num_id = _parse_team_identifier(team_id)
        if team_type == "project":
            target_project_id = num_id
            target_employee.project_id = num_id

    if not target_project_id:
        active_proj = db.query(Project).filter(Project.status == "active").first()
        if active_proj:
            target_project_id = active_proj.id
            target_employee.project_id = active_proj.id

    sprint = None
    sprint_task_id = None
    if target_project_id:
        today_date = datetime.now(timezone.utc).date()
        sprint = db.query(Sprint).filter(
            Sprint.project_id == target_project_id,
            Sprint.status == "active",
        ).first()

        if not sprint:
            planned_sprints = db.query(Sprint).filter(
                Sprint.project_id == target_project_id,
                Sprint.status == "planned",
            ).order_by(Sprint.start_date.asc()).all()

            for ps in planned_sprints:
                if ps.start_date <= today_date <= ps.end_date:
                    ps.status = "active"
                    sprint = ps
                    break
            if not sprint and planned_sprints:
                sprint = planned_sprints[0]
                sprint.status = "active"

        if not sprint:
            end_d = parsed_deadline if (parsed_deadline and parsed_deadline >= today_date) else (today_date + timedelta(days=7))
            sprint = Sprint(
                project_id=target_project_id,
                name=f"Sprint {today_date.strftime('%b %d')}",
                start_date=today_date,
                end_date=end_d,
                status="active",
                created_by=target_employee.id,
            )
            db.add(sprint)
            db.flush()

        # Add or update task in Sprint "To Do"
        inc_prefix = f"[INC-{incident.id}]"
        existing_task = db.query(SprintTask).filter(
            SprintTask.sprint_id == sprint.id,
            SprintTask.title.startswith(inc_prefix),
        ).first()

        task_title = f"{inc_prefix} {incident.title}"
        if len(task_title) > 200:
            task_title = task_title[:197] + "..."

        task_desc = f"Incident #{incident.id} ({incident.severity.upper()}):\n{incident.description}"
        if notes:
            task_desc += f"\n\nAssignment Notes: {notes}"
        if parsed_deadline:
            task_desc += f"\nDeadline: {parsed_deadline.isoformat()}"

        if existing_task:
            existing_task.assignee_id = target_employee.id
            existing_task.due_date = parsed_deadline or existing_task.due_date
            existing_task.description = task_desc
            existing_task.status = "todo"
            sprint_task_id = existing_task.id
        else:
            new_task = SprintTask(
                sprint_id=sprint.id,
                assignee_id=target_employee.id,
                title=task_title,
                description=task_desc,
                status="todo",
                progress_percent=0,
                due_date=parsed_deadline,
            )
            db.add(new_task)
            db.flush()
            sprint_task_id = new_task.id

    # 8. Record timeline entry
    override_suffix = f" (Overrode AI recommendation '{ai_team}')" if is_override else ""
    tl_note = notes if notes else f"Assigned to {target_user.full_name} [{team_name}]{override_suffix}."
    if notes and is_override:
        tl_note += f" [Overrode AI recommended team: '{ai_team}']"
    if parsed_deadline:
        tl_note += f" [Deadline: {parsed_deadline.isoformat()}]"
    if sprint:
        tl_note += f" [Added to Sprint '{sprint.name}' in To Do]"

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_assigned",
        actor_id=actor_id,
        notes=tl_note,
    )

    # 9. Record audit log
    action_name = "incident.assigned_override" if is_override else "incident.assigned"
    audit.label(db, incident, action_name)
    audit.record_event(
        db,
        action=action_name,
        entity_type="incident",
        entity_id=incident.id,
        before={
            "assigned_to": old_assignee_id,
            "assignee_name": old_user.full_name if old_user else None,
            "team_name": old_team_name,
        },
        after={
            "assigned_to": target_user.id,
            "assignee_name": target_user.full_name,
            "team_id": str(team_id) if team_id is not None else None,
            "team_name": team_name,
            "ai_recommended_team": ai_team,
            "is_override": is_override,
            "deadline": parsed_deadline.isoformat() if parsed_deadline else None,
            "sprint_id": sprint.id if sprint else None,
            "sprint_task_id": sprint_task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        actor=actor_user,
    )

    db.commit()
    db.refresh(incident)
    return get_incident(db, incident.id)


# ------------------------------------------------------------------ #
# Resolve
# ------------------------------------------------------------------ #

def resolve_incident(
    db: Session, incident_id: int, root_cause: str,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)

    if incident.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot resolve a closed incident. Reopen it first.",
        )
    if incident.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident is already resolved.",
        )

    incident.status      = "resolved"
    incident.root_cause  = root_cause
    incident.resolved_at = datetime.utcnow()

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_resolved",
        actor_id=actor_id,
        notes=notes or f"Resolved. Root cause: {root_cause[:200]}",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Close
# ------------------------------------------------------------------ #

def close_incident(
    db: Session, incident_id: int,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)

    if incident.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident is already closed.",
        )
    if incident.status not in ("resolved", "investigating", "open"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot close incident with status '{incident.status}'.",
        )

    incident.status = "closed"
    # Set resolved_at if not already set (e.g. closed without formal resolution)
    if not incident.resolved_at:
        incident.resolved_at = datetime.utcnow()

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_closed",
        actor_id=actor_id,
        notes=notes or "Incident closed.",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Delete (hard delete — Incident model has no deleted_at)
# ------------------------------------------------------------------ #

def delete_incident(db: Session, incident_id: int) -> None:
    """Hard delete. Timeline + triage rows are removed by CASCADE."""
    incident = get_incident_or_404(db, incident_id)
    db.delete(incident)
    db.commit()


# ------------------------------------------------------------------ #
# Timeline
# ------------------------------------------------------------------ #

def get_incident_timeline(db: Session, incident_id: int) -> List[IncidentTimeline]:
    get_incident_or_404(db, incident_id)   # raises 404 if missing
    return (
        db.query(IncidentTimeline)
        .filter(IncidentTimeline.incident_id == incident_id)
        .order_by(IncidentTimeline.created_at.asc())
        .all()
    )


# ------------------------------------------------------------------ #
# AI Triage
# ------------------------------------------------------------------ #

_TRIAGE_PROMPT_TEMPLATE = """\
You are an expert IT incident triage assistant.

Analyze the following incident and respond with ONLY a valid JSON object.
Do not include markdown, code fences, or any text outside the JSON.

Incident Title: {title}
Affected System: {affected_system}
Description:
{description}

Return this exact JSON structure:
{{
  "suggested_severity": "low|medium|high|critical",
  "suggested_owner": "Team or role name best suited to handle this, or null",
  "reasoning": "Concise explanation of your severity assessment and owner recommendation",
  "confidence": <number between 0.0 and 100.0>
}}

Rules:
- suggested_severity must be exactly one of: low, medium, high, critical
- confidence must be a number (not a string)
- Do not invent details not present in the incident description
- reasoning must be under 500 characters
"""


def run_ai_triage(db: Session, incident_id: int) -> IncidentAITriage:
    """
    Send incident details to Gemini, parse the structured JSON response,
    store in incident_ai_triage, and record the action in timeline.

    Raises HTTPException on configuration, API, or parse errors.
    """
    incident = get_incident_or_404(db, incident_id)

    # ── Check API key ─────────────────────────────────────────────
    api_key = settings.GEMINI_API_KEY
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured.",
        )

    # ── Build prompt ──────────────────────────────────────────────
    prompt = _TRIAGE_PROMPT_TEMPLATE.format(
        title=incident.title,
        affected_system=incident.affected_system or "Not specified",
        description=incident.description,
    )

    # ── Call Gemini ──────────────────────────────────────────────
    if _genai is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini SDK (google-genai) is not installed.",
        )
    try:
        client   = _genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        raw_text = response.text.strip()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {exc}",
        )

    # ── Parse JSON response ───────────────────────────────────────
    # Strip markdown fences if Gemini adds them despite instructions
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.DOTALL).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini returned non-JSON response: {raw_text[:300]}",
        )

    # ── Validate required fields ──────────────────────────────────
    valid_severities = {"low", "medium", "high", "critical"}
    suggested_severity = str(data.get("suggested_severity", "medium")).lower().strip()
    if suggested_severity not in valid_severities:
        suggested_severity = "medium"   # safe fallback

    suggested_owner = data.get("suggested_owner")
    if suggested_owner:
        suggested_owner = str(suggested_owner)[:120]

    reasoning = str(data.get("reasoning", "No reasoning provided."))[:2000]

    raw_confidence = data.get("confidence")
    try:
        confidence = float(raw_confidence)
        confidence = max(0.0, min(100.0, confidence))   # clamp to valid range
    except (TypeError, ValueError):
        confidence = None

    # ── Persist triage result ─────────────────────────────────────
    triage = IncidentAITriage(
        incident_id=incident_id,
        suggested_severity=suggested_severity,
        suggested_owner=suggested_owner,
        reasoning=reasoning,
        confidence=confidence,
        ai_model="gemini-3.6-flash",
    )
    db.add(triage)

    # ── Timeline entry (actor_id=None → AI action) ────────────────
    _add_timeline(
        db,
        incident_id=incident_id,
        action="ai_triage_completed",
        actor_id=None,
        notes=(
            f"AI suggested severity: '{suggested_severity}', "
            f"owner: '{suggested_owner or 'N/A'}', "
            f"confidence: {confidence:.1f}%" if confidence is not None
            else f"AI suggested severity: '{suggested_severity}'."
        ),
    )

    db.commit()
    db.refresh(triage)
    return triage


def get_latest_triage(db: Session, incident_id: int) -> IncidentAITriage:
    """Return the most recent AI triage for an incident, or 404."""
    get_incident_or_404(db, incident_id)
    triage = (
        db.query(IncidentAITriage)
        .filter(IncidentAITriage.incident_id == incident_id)
        .order_by(IncidentAITriage.generated_at.desc())
        .first()
    )
    if not triage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI triage found for incident id={incident_id}.",
        )
    return triage


# ------------------------------------------------------------------ #
# Statistics
# ------------------------------------------------------------------ #

def get_incident_stats(db: Session) -> dict:
    """Compute real statistics from the database — no hardcoded values."""

    total         = db.query(Incident).count()
    open_count    = db.query(Incident).filter(Incident.status == "open").count()
    investigating = db.query(Incident).filter(Incident.status == "investigating").count()
    resolved      = db.query(Incident).filter(Incident.status == "resolved").count()
    closed        = db.query(Incident).filter(Incident.status == "closed").count()

    sev_low      = db.query(Incident).filter(Incident.severity == "low").count()
    sev_medium   = db.query(Incident).filter(Incident.severity == "medium").count()
    sev_high     = db.query(Incident).filter(Incident.severity == "high").count()
    sev_critical = db.query(Incident).filter(Incident.severity == "critical").count()

    # Average resolution time in minutes (only for incidents with resolved_at set)
    avg_minutes: Optional[float] = None
    rows = (
        db.query(Incident.created_at, Incident.resolved_at)
        .filter(Incident.resolved_at.isnot(None))
        .all()
    )
    if rows:
        total_seconds = sum(
            (
                (row.resolved_at.replace(tzinfo=None) if row.resolved_at else None) -
                (row.created_at.replace(tzinfo=None)  if row.created_at  else None)
            ).total_seconds()
            for row in rows
            if row.resolved_at and row.created_at
        )
        avg_minutes = round(total_seconds / 60 / len(rows), 2)

    return {
        "total":         total,
        "open":          open_count,
        "investigating": investigating,
        "resolved":      resolved,
        "closed":        closed,
        "severity_low":      sev_low,
        "severity_medium":   sev_medium,
        "severity_high":     sev_high,
        "severity_critical": sev_critical,
        "avg_resolution_minutes": avg_minutes,
    }
