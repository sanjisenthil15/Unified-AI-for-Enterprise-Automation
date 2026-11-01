"""
modules/analytics/router.py

FastAPI router for the Centralized Analytics Dashboard module.

Endpoints:
    GET /analytics/overview    — Executive organizational overview (Admin, Manager, Viewer read-only)
    Viewer also reads /projects, /operations and /trends (aggregates only) — never /workforce,
    which lists named employees' workloads.
    GET /analytics/projects    — Project performance, task distribution, health
    GET /analytics/workforce   — Workforce allocations, department distribution, attendance
    GET /analytics/operations  — Incident, support, recruitment, and meeting intelligence metrics
    GET /analytics/trends      — Daily chronological trend metrics for Recharts
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from config.database import get_db
from core.authorization import assert_project_manager
from core.dependencies import (
    get_current_employee_optional,
    get_current_user,
    require_roles,
)
from core.permissions import ANALYTICS_AGGREGATE_READ_ROLES, ANALYTICS_ORG_ROLES, ROLE_ADMIN, ROLE_MANAGER
from models.employee import Employee
from models.user import User

from modules.analytics import service
from modules.analytics.schemas import (
    AnalyticsOverviewResponse,
    AnalyticsTrendsResponse,
    OperationsAnalyticsResponse,
    ProjectAnalyticsResponse,
    WorkforceAnalyticsResponse,
)

router = APIRouter(prefix="/analytics", tags=["Analytics Dashboard"])


# --------------------------------------------------------------------------- #
# Authorization helper for project-scoped analytics
# --------------------------------------------------------------------------- #

def _has_org_scope(current_user: User, *, aggregate_only: bool = False) -> bool:
    """Organization-wide (all-project) access: Admin and Manager, plus the
    read-only Viewer on aggregate-only endpoints (aggregate_only=True).

    Deliberately not core.authorization._has_override(): that also covers
    HR Managers, whose override is for HR work — not executive analytics.
    """
    roles = ANALYTICS_AGGREGATE_READ_ROLES if aggregate_only else ANALYTICS_ORG_ROLES
    return getattr(current_user.role, "name", None) in roles


def _authorize_project_scope(
    db: Session,
    current_user: User,
    current_employee: Optional[Employee],
    project_id: Optional[int],
    *,
    aggregate_only: bool = False,
) -> Optional[int]:
    """Ensures caller has rights to view organization-wide or project-specific data.

    - Admin and Manager have organization-wide override.
    - Team Leaders must supply their own project_id and are rejected on others.
    - Other roles receive HTTP 403 Forbidden.
    """
    if _has_org_scope(current_user, aggregate_only=aggregate_only):
        return project_id

    # Non-override caller (e.g., Team Leader)
    if current_employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee profile required to access project analytics.",
        )

    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team Leaders must specify their assigned project_id.",
        )

    assert_project_manager(db, current_user, current_employee, project_id)
    return project_id


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Executive organization-wide analytics overview (Admin, Manager; Viewer read-only)",
)
def get_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ANALYTICS_AGGREGATE_READ_ROLES)),
):
    """Returns top-level executive metrics across all enterprise modules."""
    return service.get_analytics_overview(db)


@router.get(
    "/projects",
    response_model=ProjectAnalyticsResponse,
    summary="Project performance, task completion status, and health indicators",
)
def get_projects_analytics(
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Returns project-level task breakdowns.

    Admin and Manager can view all projects or filter by project_id.
    Team Leaders may only view their assigned project.
    """
    scoped_id = _authorize_project_scope(db, current_user, current_employee, project_id, aggregate_only=True)
    return service.get_project_analytics(db, scoped_id)


@router.get(
    "/workforce",
    response_model=WorkforceAnalyticsResponse,
    summary="Workforce allocations, department distribution, and attendance rates",
)
def get_workforce_analytics(
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Returns workforce and workload distributions.

    Admin and Manager can view all projects or filter by project_id.
    Team Leaders may only view their assigned project.
    """
    scoped_id = _authorize_project_scope(db, current_user, current_employee, project_id)
    return service.get_workforce_analytics(db, scoped_id)


@router.get(
    "/operations",
    response_model=OperationsAnalyticsResponse,
    summary="Cross-module metrics for incidents, support, recruitment, and meetings",
)
def get_operations_analytics(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(ANALYTICS_AGGREGATE_READ_ROLES)),
):
    """Returns cross-module operational statistics."""
    return service.get_operations_analytics(db)


@router.get(
    "/trends",
    response_model=AnalyticsTrendsResponse,
    summary="Daily time-series metrics for chart visualizations",
)
def get_analytics_trends(
    range_days: int = Query(14, ge=7, le=90, description="Number of past days (7-90)"),
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Returns daily time-series counts for Recharts."""
    scoped_id = _authorize_project_scope(db, current_user, current_employee, project_id, aggregate_only=True)
    return service.get_analytics_trends(db, range_days=range_days, project_id=scoped_id)
