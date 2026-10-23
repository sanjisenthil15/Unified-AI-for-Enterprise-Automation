"""
modules/sprints/router.py

FastAPI router for the Sprints module.

Endpoints:
    POST  /sprints                         — create a sprint (that project's team lead, or admin/hr_manager)
    GET   /sprints?project_id=              — list a project's sprints (project members + manager)
    GET   /sprints/{id}                     — get one sprint (project members + manager)
    PATCH /sprints/{id}                     — edit a sprint (manager only)
    POST  /sprints/{id}/tasks               — create a task (manager only)
    GET   /sprints/{id}/tasks               — list a sprint's tasks (project members + manager)
    PATCH /sprints/tasks/{task_id}          — update a task (assignee: status/progress/description; manager: + title/assignee/due_date)
    GET   /sprints/tasks/me                  — the caller's own assigned tasks (any employee)
    GET   /sprints/{id}/burndown             — burndown chart data (project members + manager)
    GET   /sprints/review?project_id=        — manager review of the whole team (manager only)
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_employee, get_current_employee_optional, get_current_user, require_roles
from models.employee import Employee
from models.user import User

from modules.sprints.schemas import (
    BurndownPoint,
    EnterpriseOverviewEntry,
    GenerateWeeklySprintsRequest,
    ManagerReviewEntry,
    SprintCreate,
    SprintResponse,
    SprintTaskCreate,
    SprintTaskResponse,
    SprintTaskUpdate,
    SprintUpdate,
)
from modules.sprints import service

router = APIRouter(prefix="/sprints", tags=["Sprints"])


# ------------------------------------------------------------------ #
# Sprints
# ------------------------------------------------------------------ #

@router.post("", response_model=SprintResponse, status_code=201, summary="Create a sprint (that project's team lead, or admin/hr_manager)")
def create_sprint(
    payload: SprintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.create_sprint(db, current_user, current_employee, payload)


@router.get("", response_model=List[SprintResponse], summary="List a project's sprints")
def list_sprints(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.list_sprints(db, current_user, current_employee, project_id)


@router.get("/tasks/me", response_model=List[SprintTaskResponse], summary="The caller's own assigned tasks")
def list_my_tasks(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.list_my_tasks(db, current_employee, status_filter)


@router.patch("/tasks/{task_id}", response_model=SprintTaskResponse, summary="Update a task")
def update_task(
    task_id: int,
    payload: SprintTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.update_task(db, current_user, current_employee, task_id, payload)


@router.get("/review", response_model=List[ManagerReviewEntry], summary="Manager review of the whole team (manager only)")
def manager_review(
    project_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.build_manager_review(db, current_user, current_employee, project_id, start_date, end_date)


@router.post("/generate-weekly", response_model=List[SprintResponse], summary="Auto-generate weekly sprint shells up to the project's deadline (manager only)")
def generate_weekly_sprints(
    payload: GenerateWeeklySprintsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.generate_weekly_sprints(db, current_user, current_employee, payload.project_id)


@router.get("/overview", response_model=List[EnterpriseOverviewEntry], summary="Every project at a glance (admin / hr_manager only)")
def enterprise_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(["admin", "hr_manager"])),
):
    return service.build_enterprise_overview(db)


@router.get("/{sprint_id}", response_model=SprintResponse, summary="Get one sprint")
def get_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    sprint = service.get_sprint(db, sprint_id)
    service.assert_can_view_sprint(db, current_user, current_employee, sprint)
    return sprint


@router.patch("/{sprint_id}", response_model=SprintResponse, summary="Edit a sprint (manager only)")
def update_sprint(
    sprint_id: int,
    payload: SprintUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.update_sprint(db, current_user, current_employee, sprint_id, payload)


@router.post("/{sprint_id}/tasks", response_model=SprintTaskResponse, status_code=201, summary="Create a task (manager only)")
def create_task(
    sprint_id: int,
    payload: SprintTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.create_task(db, current_user, current_employee, sprint_id, payload)


@router.get("/{sprint_id}/tasks", response_model=List[SprintTaskResponse], summary="List a sprint's tasks")
def list_tasks(
    sprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.list_tasks(db, current_user, current_employee, sprint_id)


@router.get("/{sprint_id}/burndown", response_model=List[BurndownPoint], summary="Burndown chart data")
def get_burndown(
    sprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.get_burndown(db, current_user, current_employee, sprint_id)
