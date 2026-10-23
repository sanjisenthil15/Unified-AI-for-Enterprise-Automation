"""
modules/sprints/schemas.py

Pydantic schemas for the Sprints module (sprints, tasks, manager review,
burndown).
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

SPRINT_STATUSES = ("planned", "active", "completed")
TASK_STATUSES = ("todo", "in_progress", "blocked", "done")


# ------------------------------------------------------------------ #
# Sprints
# ------------------------------------------------------------------ #

class SprintCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=2, max_length=150)
    start_date: date
    end_date: date


class SprintUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(" + "|".join(SPRINT_STATUSES) + ")$")


class SprintProjectInfo(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class SprintResponse(BaseModel):
    id: int
    project: SprintProjectInfo
    name: str
    start_date: date
    end_date: date
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# Tasks
# ------------------------------------------------------------------ #

class SprintTaskCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[date] = None


class SprintTaskUpdate(BaseModel):
    """One schema accepting every updatable field — FastAPI parses the
    body before any auth check can run, so the self-vs-manager
    restriction (assignee may only touch status/progress_percent/
    description; title/assignee_id/due_date are manager-only) is
    enforced in modules/sprints/service.py, not at the schema level."""
    status: Optional[str] = Field(None, pattern="^(" + "|".join(TASK_STATUSES) + ")$")
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    description: Optional[str] = None
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    assignee_id: Optional[int] = None
    due_date: Optional[date] = None


class SprintTaskAssigneeInfo(BaseModel):
    id: int
    user_id: int
    employee_code: str
    full_name: str


class SprintTaskResponse(BaseModel):
    id: int
    sprint_id: int
    title: str
    description: Optional[str] = None
    status: str
    progress_percent: int
    due_date: Optional[date] = None
    assignee: Optional[SprintTaskAssigneeInfo] = None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ #
# Manager review
# ------------------------------------------------------------------ #

class ManagerReviewEntry(BaseModel):
    employee: SprintTaskAssigneeInfo
    checkin_rate: float
    tasks_total: int
    tasks_done: int
    tasks_overdue_incomplete: int
    completion_rate: float
    flagged: bool


# ------------------------------------------------------------------ #
# Burndown
# ------------------------------------------------------------------ #

class BurndownPoint(BaseModel):
    date: date
    remaining: int
    total: int

    model_config = {"from_attributes": True}
