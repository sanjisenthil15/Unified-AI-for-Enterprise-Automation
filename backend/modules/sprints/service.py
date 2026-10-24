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

from modules.attendance.service import compute_checkin_rates_for_employees
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


def generate_weekly_sprints(db: Session, current_user: User, current_employee: Employee | None, project_id: int) -> list[Sprint]:
    """Fills weekly Sprint *shells* up to the project's deadline (manual
    re-trigger, e.g. to fill the gap after a deadline is pushed out).
    Authorization wrapper around _generate_weekly_sprints_for_project —
    see that function for what it actually does."""
    project = _get_project(db, project_id)
    if not _is_manager(current_user, current_employee, project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only this project's team lead (or admin/hr_manager) can generate sprints.")
    if project.deadline is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This project has no deadline set yet — set one first.")
    return _generate_weekly_sprints_for_project(db, project, current_employee)


def _generate_weekly_sprints_for_project(db: Session, project: Project, current_employee: Employee | None) -> list[Sprint]:
    """Fills weekly Sprint *shells* (named "Week N") from today (or the
    last existing sprint's end_date, for idempotency) up to the project's
    deadline — it does not invent task content, only the schedule. The
    manager still creates the actual tasks, manually or by converting
    meeting action items (see modules/meeting_intelligence). No
    authorization check here — callers are either generate_weekly_sprints
    (checked above) or employee_management.service.create_project, which
    is already behind an admin/hr_manager-only route."""
    last_sprint = (
        db.query(Sprint)
        .filter(Sprint.project_id == project.id)
        .order_by(Sprint.end_date.desc())
        .first()
    )
    existing_count = db.query(Sprint).filter(Sprint.project_id == project.id).count()
    cursor = (last_sprint.end_date + timedelta(days=1)) if last_sprint else datetime.utcnow().date()

    created = []
    week_number = existing_count + 1
    while cursor <= project.deadline:
        week_end = min(cursor + timedelta(days=6), project.deadline)
        sprint = Sprint(
            project_id=project.id,
            name=f"Week {week_number}",
            start_date=cursor,
            end_date=week_end,
            status="planned",
            created_by=current_employee.id if current_employee is not None else None,
        )
        db.add(sprint)
        created.append(sprint)
        cursor = week_end + timedelta(days=1)
        week_number += 1

    db.commit()
    for s in created:
        db.refresh(s)
    return [get_sprint(db, s.id) for s in created]


def _sync_sprint_statuses(db: Session, sprints: list[Sprint]) -> None:
    """Lazy, request-time status transition — no cron exists in this app
    (same pattern as the burndown snapshot and overdue-task notification):
    the sprint covering today becomes 'active' (so the burndown chart has
    something to attach to and the board shows which week is "now"), and
    any sprint whose end_date has passed becomes 'completed'. Never
    touches a sprint a manager already moved by hand to e.g. 'blocked'-
    adjacent states — only advances out of 'planned'/'active'.

    Takes an already-fetched list (list_sprints needs these rows anyway)
    rather than querying again — this used to run a second full query
    against the same table on every single call, doubling the DB
    round-trips for one of the most frequently-hit endpoints in the app."""
    today = datetime.utcnow().date()
    changed = False
    for sprint in sprints:
        if sprint.status == "completed":
            continue
        if sprint.end_date < today:
            sprint.status = "completed"
            changed = True
        elif sprint.start_date <= today <= sprint.end_date and sprint.status == "planned":
            sprint.status = "active"
            changed = True
    if changed:
        db.commit()


def list_sprints(db: Session, current_user: User, current_employee: Employee | None, project_id: int) -> list[Sprint]:
    project = _get_project(db, project_id)
    if not _is_project_member_or_manager(current_user, current_employee, project):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You're not a member of this project.")
    sprints = (
        db.query(Sprint)
        .options(joinedload(Sprint.project))
        .filter(Sprint.project_id == project_id)
        .order_by(Sprint.start_date.desc())
        .all()
    )
    _sync_sprint_statuses(db, sprints)
    return sprints


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

def _notify_newly_overdue(db: Session, project: Project, overdue_tasks: list[SprintTask]) -> None:
    """Lazy, request-time check (no cron exists in this app — same pattern
    as the burndown snapshot): notify the project's team lead once per
    task the first time it's seen overdue, never again after that."""
    if project.team_lead is None:
        return
    for task in overdue_tasks:
        if task.overdue_notified_at is not None:
            continue
        assignee_name = task.assignee.user.full_name if task.assignee else "Unassigned"
        create_notification(
            db, project.team_lead.user_id, "task_overdue",
            f"Task '{task.title}' assigned to {assignee_name} is overdue — consider extending the deadline.",
            f"/sprints?project_id={project.id}",
        )
        task.overdue_notified_at = datetime.utcnow()
    db.commit()


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

    members = db.query(Employee).options(joinedload(Employee.user)).filter(
        Employee.project_id == project_id, Employee.deleted_at.is_(None),
    ).all()
    member_ids = [m.id for m in members]

    # Two queries total for the whole team, not two per member.
    checkin_rates = compute_checkin_rates_for_employees(db, member_ids, start, end)
    all_tasks = db.query(SprintTask).join(Sprint).filter(Sprint.project_id == project_id).all()
    tasks_by_assignee: dict[int, list[SprintTask]] = {}
    for t in all_tasks:
        if t.assignee_id is not None:
            tasks_by_assignee.setdefault(t.assignee_id, []).append(t)

    entries = []
    all_overdue_tasks = []
    for member in members:
        checkin_rate = checkin_rates.get(member.id, 1.0)
        tasks = tasks_by_assignee.get(member.id, [])
        tasks_total = len(tasks)
        tasks_done = len([t for t in tasks if t.status == "done"])
        overdue_tasks = [t for t in tasks if t.status != "done" and t.due_date is not None and t.due_date < today]
        tasks_overdue_incomplete = len(overdue_tasks)
        completion_rate = (tasks_done / tasks_total) if tasks_total else 0.0
        flagged = checkin_rate < ATTENDANCE_FLAG_THRESHOLD or tasks_overdue_incomplete >= OVERDUE_TASK_FLAG_THRESHOLD

        all_overdue_tasks.extend(overdue_tasks)

        entries.append({
            "employee": {"id": member.id, "user_id": member.user_id, "employee_code": member.employee_code, "full_name": member.user.full_name},
            "checkin_rate": checkin_rate,
            "tasks_total": tasks_total,
            "tasks_done": tasks_done,
            "tasks_overdue_incomplete": tasks_overdue_incomplete,
            "completion_rate": completion_rate,
            "flagged": flagged,
        })

    _notify_newly_overdue(db, project, all_overdue_tasks)

    entries.sort(key=lambda e: e["flagged"], reverse=True)
    return entries


# ------------------------------------------------------------------ #
# Admin: enterprise-wide project overview
# ------------------------------------------------------------------ #

def build_enterprise_overview(db: Session) -> list[dict]:
    """Every project at a glance — team lead, deadline, active sprint,
    aggregate task completion, and flagged-employee count. Admin/hr_manager
    only (enforced in the router via require_roles, not a per-project check
    — this view is explicitly enterprise-wide).

    Deliberately batched into a handful of queries total rather than
    per-project/per-employee — on a hosted Postgres instance where every
    round-trip pays real network latency, looping one query per employee
    across every project in the company made this page the single
    slowest thing in the app."""
    projects = db.query(Project).options(joinedload(Project.team_lead).joinedload(Employee.user)).order_by(Project.name).all()
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=7)

    all_members = db.query(Employee).filter(Employee.project_id.isnot(None), Employee.deleted_at.is_(None)).all()
    members_by_project: dict[int, list[Employee]] = {}
    for m in all_members:
        members_by_project.setdefault(m.project_id, []).append(m)

    checkin_rates = compute_checkin_rates_for_employees(db, [m.id for m in all_members], week_start, today)

    all_tasks_with_project = db.query(SprintTask, Sprint.project_id).join(Sprint).all()
    tasks_by_project: dict[int, list[SprintTask]] = {}
    for task, project_id in all_tasks_with_project:
        tasks_by_project.setdefault(project_id, []).append(task)

    active_sprints = db.query(Sprint).filter(Sprint.status == "active").order_by(Sprint.end_date).all()
    active_sprint_by_project: dict[int, Sprint] = {}
    for s in active_sprints:
        active_sprint_by_project.setdefault(s.project_id, s)

    overview = []
    for project in projects:
        members = members_by_project.get(project.id, [])
        tasks = tasks_by_project.get(project.id, [])
        active_sprint = active_sprint_by_project.get(project.id)

        tasks_total = len(tasks)
        tasks_done = len([t for t in tasks if t.status == "done"])
        completion_rate = (tasks_done / tasks_total) if tasks_total else 0.0

        flagged_count = 0
        for member in members:
            checkin_rate = checkin_rates.get(member.id, 1.0)
            overdue = len([
                t for t in tasks
                if t.assignee_id == member.id and t.status != "done" and t.due_date is not None and t.due_date < today
            ])
            if checkin_rate < ATTENDANCE_FLAG_THRESHOLD or overdue >= OVERDUE_TASK_FLAG_THRESHOLD:
                flagged_count += 1

        overview.append({
            "project_id": project.id,
            "project_name": project.name,
            "deadline": project.deadline,
            "team_lead": (
                {"id": project.team_lead.id, "full_name": project.team_lead.user.full_name}
                if project.team_lead else None
            ),
            "member_count": len(members),
            "active_sprint": (
                {"id": active_sprint.id, "name": active_sprint.name, "end_date": active_sprint.end_date}
                if active_sprint else None
            ),
            "completion_rate": completion_rate,
            "flagged_count": flagged_count,
        })

    return overview


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
