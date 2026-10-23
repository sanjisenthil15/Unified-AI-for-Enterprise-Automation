"""
core/authorization.py

Shared "is this person my manager" authorization rules for the
Attendance / Sprints / Manager Chat modules.

This app deliberately has no "manager" Role — leadership is represented
as org structure (Project.team_lead_id -> Employee.id), not access
control, matching the Employee Management module's existing design.
Every check here is built from that single relationship, plus the
standing admin/hr_manager override. Keeping the rule in one place avoids
each module re-implementing (and potentially drifting on) what "manager"
means.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.employee import Employee
from models.project import Project
from models.user import User

_OVERRIDE_ROLES = ("admin", "hr_manager")


def _has_override(current_user: User) -> bool:
    return current_user.role.name in _OVERRIDE_ROLES


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
    of the target employee's project. `current_employee` may be None —
    admin/hr_manager accounts often have no Employee record of their own,
    and the override check above doesn't need one."""
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
    of the given project. Used for team-wide views (attendance/sprints)
    where there's no single target employee to check against."""
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
    """True if the caller may open a chat thread with `other_user_id`:
    either side is admin/hr_manager, or the two are in a team-lead
    relationship via their project."""
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
