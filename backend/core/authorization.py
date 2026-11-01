"""
core/authorization.py

Shared "is this person my manager" authorization rules for Attendance,
Sprints, Manager Chat, and Meeting Action-Item Approval (Submodule 4.2).
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.permissions import (
    OVERRIDE_ROLES,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_HR,
    ROLE_MANAGER,
)
from models.employee import Employee
from models.project import Project
from models.user import User

_OVERRIDE_ROLES = OVERRIDE_ROLES


def _has_override(current_user: User) -> bool:
    role = getattr(current_user, "role", None)
    role_name = getattr(role, "name", role)
    return role_name in _OVERRIDE_ROLES


def is_team_lead_of(db: Session, employee: Employee, target_employee: Employee) -> bool:
    """True if `employee` is the team lead of the project `target_employee` belongs to."""
    if target_employee.project_id is None:
        return False
    project = db.query(Project).filter(Project.id == target_employee.project_id).first()
    return project is not None and project.team_lead_id == employee.id


def assert_manager_of(
    db: Session,
    current_user: User,
    current_employee: Employee | None,
    target_employee: Employee,
) -> None:
    """Raises 403 unless the caller is admin/hr_manager, or the team lead
    of the target employee's project."""
    if _has_override(current_user):
        return
    if current_employee is not None and is_team_lead_of(db, current_employee, target_employee):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "You are not the team lead of this employee's project.",
    )


def assert_project_manager(
    db: Session,
    current_user: User,
    current_employee: Employee | None,
    project_id: int,
) -> None:
    """Raises 403 unless the caller is admin/hr_manager, or the team lead
    of the given project."""
    if _has_override(current_user):
        return
    if current_employee is not None:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is not None and project.team_lead_id == current_employee.id:
            return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "You are not the team lead of this project.",
    )


def can_open_chat(
    db: Session,
    current_user: User,
    current_employee: Employee | None,
    other_user_id: int,
) -> bool:
    """True if the caller may open a chat thread with `other_user_id`."""
    if _has_override(current_user):
        return True

    other_user = db.query(User).filter(User.id == other_user_id).first()
    if other_user is not None and other_user.role.name in _OVERRIDE_ROLES:
        return True

    if current_employee is None:
        return False

    other_employee = db.query(Employee).filter(Employee.user_id == other_user_id).first()
    if other_employee is None:
        return False

    return (
        is_team_lead_of(db, current_employee, other_employee)
        or is_team_lead_of(db, other_employee, current_employee)
    )


# ------------------------------------------------------------------ #
# Meeting Intelligence & Action-Item Approval (Submodule 4.2)
# ------------------------------------------------------------------ #

def assert_can_link_project_meeting(
    db: Session,
    project_id: int | None,
    current_user: User,
    current_employee: Employee | None,
) -> None:
    """
    Validates project existence and creator authorization when linking a meeting:
      - project_id is None: Allowed (unlinked meeting; creator-only visibility).
      - project_id provided:
          * Project must exist (404 if missing).
          * Admin: Allowed across all projects.
          * Manager: Allowed ONLY if assigned as Manager of this project.
          * Team Lead: Allowed ONLY if designated team lead of this project.
          * Employee: Allowed ONLY if active member assigned to this project.
          * All other roles / unauthorized users: 403 Forbidden.
    """
    if project_id is None:
        return

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Project id={project_id} not found.",
        )

    role_name = getattr(current_user.role, "name", None)

    if role_name == ROLE_ADMIN:
        return

    if role_name == ROLE_MANAGER:
        if project.manager_user_id == current_user.id:
            return
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You are not assigned as the Manager of this project.",
        )

    if current_employee is not None and project.team_lead_id == current_employee.id:
        return

    if (
        current_employee is not None
        and current_employee.project_id == project_id
        and current_employee.status == "active"
        and role_name == ROLE_EMPLOYEE
    ):
        return

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "You are not authorized to create or link meetings for this project.",
    )


def assert_can_view_meeting(
    db: Session,
    meeting,
    current_user: User,
    current_employee: Employee | None,
) -> None:
    """
    Enforces meeting visibility matrix (Submodule 4.2):
      - Unlinked meeting: Creator-only (or Admin).
      - Project-linked meeting:
          * Admin: All projects.
          * Manager: Assigned projects only (project.manager_user_id == user.id).
          * Team Lead: Assigned project only (project.team_lead_id == employee.id).
          * Project Employee: Assigned project only (employee.project_id == meeting.project_id), read-only.
          * Otherwise: 403 Forbidden (or 404 for unlinked non-owner).
    """
    role_name = getattr(current_user.role, "name", None)

    if meeting.project_id is None:
        if meeting.created_by == current_user.id:
            return
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Meeting id={meeting.id} not found.")

    if role_name == ROLE_ADMIN:
        return

    project = meeting.project or db.query(Project).filter(Project.id == meeting.project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting project not found.")

    if role_name == ROLE_MANAGER and project.manager_user_id == current_user.id:
        return

    if current_employee is not None:
        if project.team_lead_id == current_employee.id:
            return
        if current_employee.project_id == meeting.project_id:
            return

    # If the user created this project-linked meeting, allow them to view it
    if meeting.created_by == current_user.id:
        return

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "You do not have permission to view meetings for this project.",
    )


def assert_can_review_action_items(
    db: Session,
    meeting,
    current_user: User,
    current_employee: Employee | None,
) -> None:
    """
    Enforces action-item review permissions:
    Only Admin, the Manager assigned to the project, or the Team Leader
    assigned to the project may confirm, reject, or convert action items.
    """
    if meeting.project_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Action items cannot be reviewed on an unlinked meeting. Link it to a project first.",
        )

    role_name = getattr(current_user.role, "name", None)

    if role_name == ROLE_ADMIN:
        return

    project = meeting.project or db.query(Project).filter(Project.id == meeting.project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting project not found.")

    if role_name == ROLE_MANAGER and project.manager_user_id == current_user.id:
        return

    if current_employee is not None and project.team_lead_id == current_employee.id:
        return

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Only the assigned Manager, Team Leader, or Admin can review action items for this project.",
    )


# ------------------------------------------------------------------ #
# Project Lifecycle Authorization (Phase 4.1)
# ------------------------------------------------------------------ #

def assert_can_view_project(
    db: Session,
    project: Project,
    current_user: User,
    current_employee: Employee | None,
) -> None:
    """
    Enforces project visibility scoping:
      - Admin & HR Manager: Full visibility across all projects.
      - Manager: Assigned projects only (project.manager_user_id == user.id).
      - Team Lead: Assigned project only (project.team_lead_id == employee.id).
      - Staff Employee: Staffed project only (employee.project_id == project.id).
      - Otherwise: 403 Forbidden.
    """
    role_name = getattr(current_user.role, "name", None)
    if role_name in (ROLE_ADMIN, ROLE_HR):
        return

    if role_name == ROLE_MANAGER and project.manager_user_id == current_user.id:
        return

    if current_employee is not None:
        if project.team_lead_id == current_employee.id:
            return
        if current_employee.project_id == project.id:
            return

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "You do not have permission to view this project.",
    )


def assert_can_manage_project(
    db: Session,
    project: Project,
    current_user: User,
) -> None:
    """
    Enforces project modification & lifecycle status change authorization:
      - Admin & HR Manager: Full management across all projects.
      - Assigned Manager: Can manage their assigned project only.
      - Team Leads & Employees: Read-only (403 Forbidden).
    """
    role_name = getattr(current_user.role, "name", None)
    if role_name in (ROLE_ADMIN, ROLE_HR):
        return

    if role_name == ROLE_MANAGER and project.manager_user_id == current_user.id:
        return

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Only Admin, HR Manager, or the assigned Manager can modify this project.",
    )


def assert_can_delete_project(
    db: Session,
    project: Project,
    current_user: User,
) -> None:
    """
    Enforces hard deletion authorization:
      - Admin & HR Manager ONLY.
      - Managers, Team Leads, Employees: 403 Forbidden.
    """
    # Deliberately narrower than _has_override(): Managers are an override
    # role elsewhere, but must not hard-delete projects.
    if getattr(current_user.role, "name", None) in (ROLE_ADMIN, ROLE_HR):
        return

    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Only administrators and HR managers can delete projects.",
    )
