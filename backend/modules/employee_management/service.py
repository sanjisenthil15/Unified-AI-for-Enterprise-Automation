"""
modules/employee_management/service.py

Business logic for the Employee Management module.

Onboarding creates a User (login account) and Employee (org record)
together in one transaction — the realistic HR flow. There's no email
integration in this app, so the generated temporary password is returned
once in the API response for HR to hand to the new hire directly.
"""

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text, or_, and_
from sqlalchemy.orm import Session, joinedload

from core import audit
from core.authorization import (
    assert_can_delete_project,
    assert_can_manage_project,
    assert_can_view_project,
)
from core.permissions import (
    OVERRIDE_ROLES,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_HR,
    ROLE_MANAGER,
)
from core.security import generate_temporary_password, hash_password
from models.department import Department
from models.employee import Employee
from models.meeting import Meeting
from models.project import Project
from models.role import Role
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.user import User

MANAGEMENT_TOPOLOGY_ADVISORY_LOCK_KEY = 420042


def _acquire_topology_lock(db: Session) -> None:
    """Acquires a PostgreSQL transaction-level advisory lock serializing all
    Manager lifecycle and project topology operations organization-wide."""
    db.execute(text(f"SELECT pg_advisory_xact_lock({MANAGEMENT_TOPOLOGY_ADVISORY_LOCK_KEY});"))


# ------------------------------------------------------------------ #
# Departments
# ------------------------------------------------------------------ #

def list_departments(db: Session) -> list[Department]:
    return db.query(Department).order_by(Department.name).all()


def create_department(db: Session, payload) -> Department:
    existing = db.query(Department).filter(Department.name == payload.name).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A department with this name already exists.")
    dept = Department(name=payload.name, description=payload.description)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


# ------------------------------------------------------------------ #
# Employees
# ------------------------------------------------------------------ #

def _employee_query(db: Session):
    return db.query(Employee).options(
        joinedload(Employee.user).joinedload(User.role),
        joinedload(Employee.department),
        joinedload(Employee.project),
    )


def list_employees(db: Session, *, department_id: int | None = None, status_filter: str | None = None) -> list[Employee]:
    query = _employee_query(db).filter(Employee.deleted_at.is_(None))
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if status_filter is not None:
        query = query.filter(Employee.status == status_filter)
    return query.order_by(Employee.created_at.desc()).all()


def get_employee(db: Session, employee_id: int) -> Employee:
    employee = _employee_query(db).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee id={employee_id} not found.")
    return employee


def get_my_employee_record(db: Session, user_id: int) -> Employee:
    employee = _employee_query(db).filter(Employee.user_id == user_id).first()
    if employee is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No employee record yet. Contact HR to be onboarded.",
        )
    return employee


def create_employee(db: Session, payload):
    """Creates the login account + employee record together. Returns
    (Employee, temporary_password)."""
    role = db.query(Role).filter(Role.id == payload.role_id).first()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Role id={payload.role_id} does not exist.")

    # Concurrency serialization for Manager onboarding
    if role.name == ROLE_MANAGER:
        _acquire_topology_lock(db)

    if payload.department_id is not None:
        dept = db.query(Department).filter(Department.id == payload.department_id).first()
        if dept is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Department id={payload.department_id} does not exist.")

    if payload.project_id is not None:
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if project is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Project id={payload.project_id} does not exist.")

    existing_user = (
        db.query(User)
        .filter(User.email == payload.email.lower(), User.deleted_at.is_(None))
        .first()
    )
    if existing_user is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email address already exists.")

    temp_password = generate_temporary_password()

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hash_password(temp_password),
        role_id=payload.role_id,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()

    employee = Employee(
        user_id=user.id,
        department_id=payload.department_id,
        project_id=payload.project_id,
        employee_code=f"EMP-{uuid.uuid4().hex[:8].upper()}",
        job_title=payload.job_title,
        phone=payload.phone,
        hire_date=payload.hire_date,
        employment_type=payload.employment_type,
        status="active",
    )
    db.add(employee)
    db.commit()

    db.refresh(employee)
    return get_employee(db, employee.id), temp_password


def update_employee(db: Session, employee_id: int, payload) -> Employee:
    data = payload.model_dump(exclude_unset=True)

    # Acquire advisory lock FIRST before reading state if role or status is being modified
    if "role_id" in data or "status" in data:
        _acquire_topology_lock(db)

    employee = _employee_query(db).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee id={employee_id} not found.")

    if "role_id" in data and data["role_id"] is not None:
        target_role = db.query(Role).filter(Role.id == data["role_id"]).first()
        if target_role is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Role id={data['role_id']} does not exist.")

        # If removing Manager role, ensure no projects are currently assigned
        if employee.user and employee.user.role and employee.user.role.name == ROLE_MANAGER and target_role.name != ROLE_MANAGER:
            assigned = db.query(Project.name).filter(Project.manager_user_id == employee.user_id).all()
            if assigned:
                names = ", ".join(f"'{p[0]}'" for p in assigned)
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Cannot remove Manager role while assigned to projects: {names}. Reassign all projects first.",
                )

        employee.user.role_id = target_role.id
        del data["role_id"]

    if "status" in data and data["status"] is not None:
        if data["status"] in ("inactive", "terminated"):
            # If deactivating a Manager, block if any projects remain assigned
            if employee.user and employee.user.role and employee.user.role.name == ROLE_MANAGER:
                assigned = db.query(Project.name).filter(Project.manager_user_id == employee.user_id).all()
                if assigned:
                    names = ", ".join(f"'{p[0]}'" for p in assigned)
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"Cannot deactivate Manager while assigned to projects: {names}. Reassign all projects first.",
                    )
            if employee.user:
                employee.user.is_active = False
        elif data["status"] == "active":
            if employee.user:
                employee.user.is_active = True

    if "department_id" in data and data["department_id"] is not None:
        dept = db.query(Department).filter(Department.id == data["department_id"]).first()
        if dept is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Department id={data['department_id']} does not exist.")
    if "project_id" in data and data["project_id"] is not None:
        project = db.query(Project).filter(Project.id == data["project_id"]).first()
        if project is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Project id={data['project_id']} does not exist.")

    for field, value in data.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)
    return get_employee(db, employee.id)


def terminate_employee(db: Session, employee_id: int) -> Employee:
    # Acquire advisory lock FIRST before reading state
    _acquire_topology_lock(db)

    employee = _employee_query(db).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee id={employee_id} not found.")

    if employee.user and employee.user.role and employee.user.role.name == ROLE_MANAGER:
        assigned = db.query(Project.name).filter(Project.manager_user_id == employee.user_id).all()
        if assigned:
            names = ", ".join(f"'{p[0]}'" for p in assigned)
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Cannot terminate Manager while assigned to projects: {names}. Reassign all projects first.",
            )

    employee.status = "terminated"
    audit.label(db, employee, "employee.terminated")
    if employee.user:
        employee.user.is_active = False
        audit.label(db, employee.user, "user.deactivated")

    db.commit()
    db.refresh(employee)
    return get_employee(db, employee.id)


# ------------------------------------------------------------------ #
# Projects
# ------------------------------------------------------------------ #

def _project_query(db: Session):
    return db.query(Project).options(
        joinedload(Project.team_lead).joinedload(Employee.user),
        joinedload(Project.manager),
    )


def _with_member_count(db: Session, project: Project) -> Project:
    project.member_count = (
        db.query(Employee)
        .filter(Employee.project_id == project.id, Employee.deleted_at.is_(None))
        .count()
    )
    return project


def list_projects(
    db: Session,
    current_user: User | None = None,
    current_employee: Employee | None = None,
) -> list[Project]:
    query = _project_query(db)
    if current_user is not None:
        role_name = getattr(current_user.role, "name", None)
        if role_name not in (ROLE_ADMIN, ROLE_HR):
            if role_name == ROLE_MANAGER:
                query = query.filter(Project.manager_user_id == current_user.id)
            elif current_employee is not None:
                query = query.filter(
                    or_(
                        Project.team_lead_id == current_employee.id,
                        Project.id == current_employee.project_id,
                    )
                )
            else:
                return []
    projects = query.order_by(Project.name).all()
    return [_with_member_count(db, p) for p in projects]


def get_project(
    db: Session,
    project_id: int,
    current_user: User | None = None,
    current_employee: Employee | None = None,
) -> Project:
    project = _project_query(db).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")
    if current_user is not None:
        assert_can_view_project(db, project, current_user, current_employee)
    return _with_member_count(db, project)


def create_project(db: Session, payload, current_employee=None) -> Project:
    existing = db.query(Project).filter(Project.name == payload.name).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A project with this name already exists.")

    initial_status = getattr(payload, "status", None) or "planning"
    if initial_status not in ("planning", "active"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "New projects can only start in 'planning' or 'active' status.",
        )

    start_date = getattr(payload, "start_date", None)
    deadline = getattr(payload, "deadline", None)
    if start_date is not None and deadline is not None and deadline < start_date:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "deadline must be on or after start_date.",
        )

    project = Project(
        name=payload.name,
        description=payload.description,
        status=initial_status,
        start_date=start_date,
        deadline=deadline,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    if project.status == "active" and project.deadline is not None:
        from modules.sprints.service import _generate_weekly_sprints_for_project
        _generate_weekly_sprints_for_project(db, project, current_employee)

    return get_project(db, project.id)


def update_project(
    db: Session,
    project_id: int,
    payload,
    current_user: User,
) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .with_for_update()
        .first()
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")

    assert_can_manage_project(db, project, current_user)

    if project.status in ("completed", "cancelled", "archived"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot edit project metadata in '{project.status}' status.",
        )

    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)

    if "name" in data and data["name"] != project.name:
        existing = db.query(Project).filter(Project.name == data["name"], Project.id != project_id).first()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A project with this name already exists.")
        project.name = data["name"]

    if "description" in data:
        project.description = data["description"]

    new_start = data.get("start_date", project.start_date)
    new_deadline = data.get("deadline", project.deadline)
    if new_start is not None and new_deadline is not None and new_deadline < new_start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "deadline must be on or after start_date.")

    if "start_date" in data:
        project.start_date = data["start_date"]
    if "deadline" in data:
        project.deadline = data["deadline"]

    db.commit()
    db.refresh(project)
    return get_project(db, project.id)


ALLOWED_TRANSITIONS = {
    "planning": {"active", "cancelled", "archived"},
    "active": {"on_hold", "completed", "cancelled", "archived"},
    "on_hold": {"active", "cancelled", "archived"},
    "completed": {"archived"},
    "cancelled": {"archived"},
    "archived": set(),
}


def update_project_status(
    db: Session,
    project_id: int,
    target_status: str,
    current_user: User,
    current_employee: Employee | None = None,
) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .with_for_update()
        .first()
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")

    assert_can_manage_project(db, project, current_user)

    if project.status == target_status:
        return get_project(db, project.id)

    valid_targets = ALLOWED_TRANSITIONS.get(project.status, set())
    if target_status not in valid_targets:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid status transition from '{project.status}' to '{target_status}'. "
            f"Reopening completed or cancelled projects is not allowed.",
        )

    now_utc = datetime.now(timezone.utc)

    if target_status == "completed":
        # Completion validation: all sprints completed, all tasks done
        uncompleted_sprints = (
            db.query(Sprint)
            .filter(Sprint.project_id == project.id, Sprint.status != "completed")
            .count()
        )
        if uncompleted_sprints > 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Cannot complete project: {uncompleted_sprints} sprint(s) are not completed.",
            )

        unresolved_tasks = (
            db.query(SprintTask)
            .join(Sprint, SprintTask.sprint_id == Sprint.id)
            .filter(Sprint.project_id == project.id, SprintTask.status != "done")
            .count()
        )
        if unresolved_tasks > 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Cannot complete project: {unresolved_tasks} task(s) are not resolved (status must be 'done').",
            )

        project.completed_at = now_utc
        project.cancelled_at = None

    elif target_status == "cancelled":
        project.cancelled_at = now_utc
        # completed_at remains untouched / None

    elif target_status == "archived":
        project.archived_at = now_utc
        # Preserves existing completed_at or cancelled_at

    elif target_status == "active":
        if project.status == "planning" and project.deadline is not None:
            sprint_count = db.query(Sprint).filter(Sprint.project_id == project.id).count()
            if sprint_count == 0:
                from modules.sprints.service import _generate_weekly_sprints_for_project
                _generate_weekly_sprints_for_project(db, project, current_employee)

    project.status = target_status
    audit.label(db, project, "project.status_changed")
    db.commit()
    db.refresh(project)
    return get_project(db, project.id)


def delete_project(db: Session, project_id: int, current_user: User) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")

    assert_can_delete_project(db, project, current_user)

    sprints_exist = db.query(Sprint).filter(Sprint.project_id == project.id).count() > 0
    meetings_exist = db.query(Meeting).filter(Meeting.project_id == project.id).count() > 0
    employees_exist = db.query(Employee).filter(Employee.project_id == project.id, Employee.deleted_at.is_(None)).count() > 0

    if sprints_exist or meetings_exist or employees_exist:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot delete project with associated sprints, meetings, or employees. Please archive the project instead.",
        )

    db.delete(project)
    db.commit()
    return {"message": f"Project id={project_id} deleted successfully."}


def assign_team_lead(db: Session, project_id: int, employee_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Employee id={employee_id} does not exist.")
    if employee.project_id != project_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The team lead must already be a member of this project — assign them to it first.",
        )
    project.team_lead_id = employee_id
    audit.label(db, project, "project.team_lead_assigned")
    db.commit()
    db.refresh(project)
    return get_project(db, project.id)


def assign_project_manager(db: Session, project_id: int, manager_user_id: int) -> Project:
    """Assigns or reassigns the designated Manager of a project under the global advisory lock."""
    _acquire_topology_lock(db)

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")

    target_user = (
        db.query(User)
        .options(joinedload(User.role))
        .filter(User.id == manager_user_id, User.deleted_at.is_(None))
        .first()
    )
    if target_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User id={manager_user_id} not found.")

    if not target_user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selected Manager user is inactive.")

    role_name = getattr(target_user.role, "name", None)
    if role_name != ROLE_MANAGER:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"User id={manager_user_id} does not have the Manager role (role is '{role_name}').",
        )

    project.manager_user_id = manager_user_id
    audit.label(db, project, "project.manager_assigned")
    db.commit()
    db.refresh(project)
    return get_project(db, project.id)
