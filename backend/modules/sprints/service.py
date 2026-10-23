"""
modules/sprints/service.py

Business logic for the Sprints module: sprints, tasks, the manager
review aggregation, and the lazily-captured burndown snapshot.
"""

from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from models.employee import Employee
from models.project import Project
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.sprint_task_snapshot import SprintTaskSnapshot
from models.user import User

from modules.attendance.service import compute_checkin_rate
from modules.notifications.service import create_notification

# A single bad day shouldn't flag someone; a sustained pattern should.
ATTENDANCE_FLAG_THRESHOLD = 0.8
OVERDUE_TASK_FLAG_THRESHOLD = 2

MANAGER_ONLY_TASK_FIELDS = {"title", "assignee_id", "due_date"}


# ------------------------------------------------------------------ #
# Access helpers
# ------------------------------------------------------------------ #

def _is_manager(current_user: User, current_employee: Employee | None, project: Project) -> bool:
    if current_user.role.name in ("admin", "hr_manager"):
        return True
    return current_employee is not None and project.team_lead_id == current_employee.id


def _is_project_member_or_manager(current_user: User, current_employee: Employee | None, project: Project) -> bool:
    if _is_manager(current_user, current_employee, project):
        return True
    return current_employee is not None and current_employee.project_id == project.id


# ------------------------------------------------------------------ #
# Sprints
# ------------------------------------------------------------------ #

def _get_project(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")
    return project


def get_sprint(db: Session, sprint_id: int) -> Sprint:
    sprint = db.query(Sprint).options(joinedload(Sprint.project)).filter(Sprint.id == sprint_id).first()
    if sprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Sprint id={sprint_id} not found.")
    return sprint


def create_sprint(db: Session, current_user: User, current_employee: Employee | None, payload) -> Sprint:
    project = _get_project(db, payload.project_id)
    if not _is_manager(current_user, current_employee, project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this project's team lead (or admin/hr_manager) can create sprints.")
    if payload.end_date < payload.start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end_date must be on or after start_date.")

    sprint = Sprint(
        project_id=project.id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="planned",
        created_by=current_employee.id if current_employee is not None else None,
    )
    db.add(sprint)
    db.commit()
    db.refresh(sprint)

    members = db.query(Employee).filter(Employee.project_id == project.id, Employee.deleted_at.is_(None)).all()
    for member in members:
        create_notification(
            db, member.user_id, "sprint_created",
            f"New sprint '{sprint.name}' scheduled for {project.name}.",
            f"/sprints?project_id={project.id}",
        )

    return get_sprint(db, sprint.id)


def list_sprints(db: Session, current_user: User, current_employee: Employee | None, project_id: int) -> list[Sprint]:
    project = _get_project(db, project_id)
    if not _is_project_member_or_manager(current_user, current_employee, project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You're not a member of this project.")
    return (
        db.query(Sprint)
        .options(joinedload(Sprint.project))
        .filter(Sprint.project_id == project_id)
        .order_by(Sprint.start_date.desc())
        .all()
    )


def assert_can_view_sprint(db: Session, current_user: User, current_employee: Employee | None, sprint: Sprint) -> None:
    project = sprint.project or _get_project(db, sprint.project_id)
    if not _is_project_member_or_manager(current_user, current_employee, project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You're not a member of this project.")


def update_sprint(db: Session, current_user: User, current_employee: Employee | None, sprint_id: int, payload) -> Sprint:
    sprint = get_sprint(db, sprint_id)
    if not _is_manager(current_user, current_employee, sprint.project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this project's team lead (or admin/hr_manager) can edit sprints.")

    data = payload.model_dump(exclude_unset=True)
    new_start = data.get("start_date", sprint.start_date)
    new_end = data.get("end_date", sprint.end_date)
    if new_end < new_start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end_date must be on or after start_date.")
    for field, value in data.items():
        setattr(sprint, field, value)

    db.commit()
    db.refresh(sprint)
    return get_sprint(db, sprint.id)


# ------------------------------------------------------------------ #
# Tasks
# ------------------------------------------------------------------ #

def _task_assignee_info(assignee: Employee | None) -> dict | None:
    if assignee is None:
        return None
    return {"id": assignee.id, "user_id": assignee.user_id, "employee_code": assignee.employee_code, "full_name": assignee.user.full_name}


def _task_response(task: SprintTask) -> dict:
    return {
        "id": task.id,
        "sprint_id": task.sprint_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "progress_percent": task.progress_percent,
        "due_date": task.due_date,
        "assignee": _task_assignee_info(task.assignee),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _task_query(db: Session):
    return db.query(SprintTask).options(joinedload(SprintTask.assignee).joinedload(Employee.user))


def create_task(db: Session, current_user: User, current_employee: Employee | None, sprint_id: int, payload) -> dict:
    sprint = get_sprint(db, sprint_id)
    if not _is_manager(current_user, current_employee, sprint.project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this project's team lead (or admin/hr_manager) can create tasks.")

    if payload.assignee_id is not None:
        assignee = db.query(Employee).filter(Employee.id == payload.assignee_id).first()
        if assignee is None or assignee.project_id != sprint.project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "assignee_id must be a member of this sprint's project.")

    task = SprintTask(
        sprint_id=sprint.id,
        assignee_id=payload.assignee_id,
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        status="todo",
        progress_percent=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    if task.assignee_id is not None:
        assignee = db.query(Employee).filter(Employee.id == task.assignee_id).first()
        create_notification(
            db, assignee.user_id, "task_assigned",
            f"You were assigned '{task.title}' in sprint '{sprint.name}'.",
            f"/sprints?project_id={sprint.project_id}",
        )

    task = _task_query(db).filter(SprintTask.id == task.id).first()
    return _task_response(task)


def list_tasks(db: Session, current_user: User, current_employee: Employee | None, sprint_id: int) -> list[dict]:
    sprint = get_sprint(db, sprint_id)
    assert_can_view_sprint(db, current_user, current_employee, sprint)
    tasks = _task_query(db).filter(SprintTask.sprint_id == sprint_id).order_by(SprintTask.created_at).all()
    return [_task_response(t) for t in tasks]


def list_my_tasks(db: Session, current_employee: Employee, status_filter: str | None) -> list[dict]:
    query = _task_query(db).filter(SprintTask.assignee_id == current_employee.id)
    if status_filter is not None:
        query = query.filter(SprintTask.status == status_filter)
    tasks = query.order_by(SprintTask.due_date.is_(None), SprintTask.due_date).all()
    return [_task_response(t) for t in tasks]


def update_task(db: Session, current_user: User, current_employee: Employee | None, task_id: int, payload) -> dict:
    task = _task_query(db).filter(SprintTask.id == task_id).first()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Sprint task id={task_id} not found.")
    sprint = get_sprint(db, task.sprint_id)

    is_manager = _is_manager(current_user, current_employee, sprint.project)
    is_assignee = current_employee is not None and task.assignee_id == current_employee.id
    if not is_manager and not is_assignee:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only update your own assigned tasks.")

    data = payload.model_dump(exclude_unset=True)
    if not is_manager:
        offending = MANAGER_ONLY_TASK_FIELDS & data.keys()
        if offending:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Only this project's team lead (or admin/hr_manager) can change: {', '.join(sorted(offending))}.",
            )

    if "assignee_id" in data and data["assignee_id"] is not None:
        new_assignee = db.query(Employee).filter(Employee.id == data["assignee_id"]).first()
        if new_assignee is None or new_assignee.project_id != sprint.project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "assignee_id must be a member of this sprint's project.")

    for field, value in data.items():
        setattr(task, field, value)
    if task.status == "done":
        task.progress_percent = 100

    db.commit()
    db.refresh(task)

    if "assignee_id" in data and data["assignee_id"] is not None:
        create_notification(
            db, task.assignee.user_id, "task_assigned",
            f"You were assigned '{task.title}' in sprint '{sprint.name}'.",
            f"/sprints?project_id={sprint.project_id}",
        )

    task = _task_query(db).filter(SprintTask.id == task.id).first()
    return _task_response(task)


# ------------------------------------------------------------------ #
# Manager review
# ------------------------------------------------------------------ #

def build_manager_review(
    db: Session, current_user: User, current_employee: Employee | None,
    project_id: int, start_date: date | None, end_date: date | None,
) -> list[dict]:
    project = _get_project(db, project_id)
    if not _is_manager(current_user, current_employee, project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this project's team lead (or admin/hr_manager) can view the team review.")

    end = end_date or datetime.utcnow().date()
    start = start_date or (end - timedelta(days=7))
    today = datetime.utcnow().date()

    members = db.query(Employee).filter(Employee.project_id == project_id, Employee.deleted_at.is_(None)).all()
    entries = []
    for member in members:
        checkin_rate = compute_checkin_rate(db, member.id, start, end)
        tasks = db.query(SprintTask).join(Sprint).filter(SprintTask.assignee_id == member.id, Sprint.project_id == project_id).all()
        tasks_total = len(tasks)
        tasks_done = len([t for t in tasks if t.status == "done"])
        tasks_overdue_incomplete = len([t for t in tasks if t.status != "done" and t.due_date is not None and t.due_date < today])
        completion_rate = (tasks_done / tasks_total) if tasks_total else 0.0
        flagged = checkin_rate < ATTENDANCE_FLAG_THRESHOLD or tasks_overdue_incomplete >= OVERDUE_TASK_FLAG_THRESHOLD

        entries.append({
            "employee": {"id": member.id, "user_id": member.user_id, "employee_code": member.employee_code, "full_name": member.user.full_name},
            "checkin_rate": checkin_rate,
            "tasks_total": tasks_total,
            "tasks_done": tasks_done,
            "tasks_overdue_incomplete": tasks_overdue_incomplete,
            "completion_rate": completion_rate,
            "flagged": flagged,
        })

    entries.sort(key=lambda e: e["flagged"], reverse=True)
    return entries


# ------------------------------------------------------------------ #
# Burndown
# ------------------------------------------------------------------ #

def get_burndown(db: Session, current_user: User, current_employee: Employee | None, sprint_id: int) -> list[dict]:
    sprint = get_sprint(db, sprint_id)
    assert_can_view_sprint(db, current_user, current_employee, sprint)

    today = datetime.utcnow().date()
    if sprint.status == "active":
        existing = (
            db.query(SprintTaskSnapshot)
            .filter(SprintTaskSnapshot.sprint_id == sprint_id, SprintTaskSnapshot.snapshot_date == today)
            .first()
        )
        if existing is None:
            tasks = db.query(SprintTask).filter(SprintTask.sprint_id == sprint_id).all()
            total = len(tasks)
            remaining = len([t for t in tasks if t.status != "done"])
            db.add(SprintTaskSnapshot(sprint_id=sprint_id, snapshot_date=today, remaining_count=remaining, total_count=total))
            db.commit()

    snapshots = (
        db.query(SprintTaskSnapshot)
        .filter(SprintTaskSnapshot.sprint_id == sprint_id)
        .order_by(SprintTaskSnapshot.snapshot_date)
        .all()
    )
    return [{"date": s.snapshot_date, "remaining": s.remaining_count, "total": s.total_count} for s in snapshots]
