"""
modules/intelligence/router.py

FastAPI router for Phase 3.3: AI-Powered Enterprise Intelligence Module.

RBAC Architecture:
  - Admin & Manager: Full organization-wide intelligence access.
  - Team Leader: Project-scoped intelligence only for their designated project.
    Cross-project requests or missing project_id where required return HTTP 403.
  - Employee: HTTP 403 Forbidden for all organization-wide and project intelligence endpoints.
  - Cache Refresh: Admin & Manager can refresh organization-wide insights.
    Team Leaders can refresh only their assigned project scope. Throttled to 10s cooldown.
"""

import logging
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
from core.permissions import ROLE_ADMIN, ROLE_MANAGER
from models.employee import Employee
from models.project import Project
from models.sprint import Sprint
from models.user import User

from modules.intelligence import service
from modules.intelligence.cache import intelligence_cache
from modules.intelligence.schemas import (
    ExecutiveSummaryResponse,
    OperationsInsightsResponse,
    ProjectRiskIntelligenceResponse,
    RefreshRequest,
    RefreshResponse,
    SprintDelayIntelligenceResponse,
    WorkloadIntelligenceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence", tags=["Enterprise AI Intelligence"])

INTELLIGENCE_ORG_ROLES = [ROLE_ADMIN, ROLE_MANAGER]


# --------------------------------------------------------------------------- #
# Authorization Helper for Project-Scoped Intelligence
# --------------------------------------------------------------------------- #

def _has_org_scope(current_user: User) -> bool:
    """Organization-wide (all-project) access is Admin and Manager only.

    Deliberately not core.authorization._has_override(): that also covers
    HR Managers, whose override is for HR work — not executive analytics.
    """
    return getattr(current_user.role, "name", None) in INTELLIGENCE_ORG_ROLES


def _authorize_project_scope(
    db: Session,
    current_user: User,
    current_employee: Optional[Employee],
    project_id: Optional[int],
) -> Optional[int]:
    """Ensures caller has rights to view organization-wide or project-specific data.

    - Admin and Manager have organization-wide override.
    - Team Leaders must supply their assigned project_id and are rejected on others.
    - Regular employees and non-leads receive HTTP 403 Forbidden.
    """
    if _has_org_scope(current_user):
        if project_id is not None:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Project with ID {project_id} not found.",
                )
        return project_id

    # Non-override caller (e.g. Team Leader or regular Employee)
    if current_employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee profile required to access project intelligence.",
        )

    if project_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team Leaders must specify their assigned project_id.",
        )

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found.",
        )

    assert_project_manager(db, current_user, current_employee, project_id)
    return project_id


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get(
    "/executive-summary",
    response_model=ExecutiveSummaryResponse,
    summary="Executive recommendations and organization brief (Admin & Manager only)",
)
def get_executive_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(INTELLIGENCE_ORG_ROLES)),
):
    """Synthesizes cross-module executive briefing and actionable 4-part recommendations.
    Strictly restricted to Admin and Manager roles."""
    return service.get_executive_recommendations(db)


@router.get(
    "/project-risks",
    response_model=ProjectRiskIntelligenceResponse,
    summary="Project delivery risk explanations and recommendations",
)
def get_project_risks(
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Returns project delivery risk insights with deterministic risk scores and levels.

    - Admin and Manager can view all projects or filter by project_id.
    - Team Leaders can only access their assigned project_id.
    - Regular employees are rejected with HTTP 403 Forbidden.
    """
    scoped_id = _authorize_project_scope(db, current_user, current_employee, project_id)
    return service.get_project_risk_insights(db, project_id=scoped_id)


@router.get(
    "/sprint-delays",
    response_model=SprintDelayIntelligenceResponse,
    summary="Sprint delay warnings grounded in verifiable delivery metrics",
)
def get_sprint_delays(
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    sprint_id: Optional[int] = Query(None, description="Optional sprint ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Returns sprint delivery trajectories without speculative predictions.

    - Admin and Manager can access organization-wide or project-specific sprints.
    - Team Leaders can only access sprints for their assigned project.
    - Cross-project sprint queries return HTTP 403 Forbidden.
    """
    scoped_id = _authorize_project_scope(db, current_user, current_employee, project_id)

    if sprint_id is not None:
        sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
        if sprint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sprint with ID {sprint_id} not found.",
            )
        if not _has_org_scope(current_user) and sprint.project_id != scoped_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access sprints outside your assigned project.",
            )

    return service.get_sprint_delay_insights(db, project_id=scoped_id, sprint_id=sprint_id)


@router.get(
    "/workload-bottlenecks",
    response_model=WorkloadIntelligenceResponse,
    summary="Role-level workload distribution and bottleneck identification",
)
def get_workload_bottlenecks(
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Identifies workload imbalances at the role and team level.
    Never exposes individual surveillance metrics or subjective productivity ratings."""
    scoped_id = _authorize_project_scope(db, current_user, current_employee, project_id)
    return service.get_workload_bottleneck_insights(db, project_id=scoped_id)


@router.get(
    "/operations-insights",
    response_model=OperationsInsightsResponse,
    summary="Cross-module support and incident operational intelligence (Admin & Manager only)",
)
def get_operations_insights(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(INTELLIGENCE_ORG_ROLES)),
):
    """Synthesizes customer support friction categories and incident vulnerability patterns.
    Strictly restricted to Admin and Manager roles."""
    return service.get_operations_insights(db)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh intelligence cache (Admin/Manager org-wide, Team Leader project scope)",
)
def refresh_intelligence_cache(
    request: Optional[RefreshRequest] = None,
    project_id: Optional[int] = Query(None, description="Optional project ID to refresh"),
    scope: Optional[str] = Query(None, description="Optional scope ('org' or 'project')"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    """Safely invalidates intelligence cache entries.

    - Admin and Manager can trigger organization-wide or project-specific refreshes.
    - Team Leaders can only refresh their assigned project scope.
    - Enforces a 10-second refresh cooldown to protect API quotas.
    """
    target_project_id = project_id if project_id is not None else (request.project_id if request else None)
    target_scope = scope if scope is not None else (
        request.scope if (request and request.scope) else ("project" if target_project_id is not None else "org")
    )

    if target_scope == "project" or target_project_id is not None:
        if target_project_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_id is required when refreshing project scope.",
            )
        project = db.query(Project).filter(Project.id == target_project_id).first()
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID {target_project_id} not found.",
            )
        if not _has_org_scope(current_user):
            if current_employee is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Employee profile required to refresh project intelligence.",
                )
            assert_project_manager(db, current_user, current_employee, target_project_id)

        throttle_key = f"intelligence:project:{target_project_id}:refresh"
    else:
        # Organization-wide refresh
        if not _has_org_scope(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Admin and Manager accounts are authorized to trigger organization-wide intelligence refresh.",
            )
        throttle_key = "intelligence:org:refresh"

    # Cooldown verification (10s window)
    allowed, remaining = intelligence_cache.check_refresh_throttle(throttle_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Refresh cooldown active. Please wait {remaining} seconds before refreshing again.",
            headers={"Retry-After": str(int(remaining) + 1)},
        )

    # Invalidate cache and record refresh timestamp
    if target_project_id is not None:
        intelligence_cache.invalidate_scope(f"intelligence:project:{target_project_id}:")
        intelligence_cache.set(throttle_key, True, ttl=10)
        return RefreshResponse(
            status="refreshed",
            message=f"Cache successfully invalidated for project {target_project_id}.",
            scope="project",
            project_id=target_project_id,
        )
    else:
        intelligence_cache.clear()
        intelligence_cache.set(throttle_key, True, ttl=10)
        return RefreshResponse(
            status="refreshed",
            message="Organization-wide intelligence cache successfully invalidated.",
            scope="org",
            project_id=None,
        )
