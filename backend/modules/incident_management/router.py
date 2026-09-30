"""
modules/incident_management/router.py

FastAPI router for the Incident Management module.
All routes are prefixed /incidents and versioned under /api/v1 in main.py.

Endpoints
---------
GET    /incidents/statistics
POST   /incidents
GET    /incidents
GET    /incidents/{incident_id}
PUT    /incidents/{incident_id}
DELETE /incidents/{incident_id}
PUT    /incidents/{incident_id}/status
PUT    /incidents/{incident_id}/assign
PUT    /incidents/{incident_id}/resolve
PUT    /incidents/{incident_id}/close
GET    /incidents/{incident_id}/timeline
POST   /incidents/{incident_id}/triage
GET    /incidents/{incident_id}/triage
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_user, require_roles
from models.user import User

from modules.incident_management import service
from modules.incident_management.schemas import (
    AITriageResponse,
    IncidentAssign,
    IncidentCreate,
    IncidentListItem,
    IncidentResolve,
    IncidentResponse,
    IncidentStats,
    IncidentStatusUpdate,
    IncidentUpdate,
    TimelineEntryResponse,
)

router = APIRouter(prefix="/incidents", tags=["Incident Management"])

_WRITE_ROLES  = ["it_engineer", "admin", "manager"]
_ASSIGN_ROLES = ["admin", "manager"]


# ------------------------------------------------------------------ #
# Statistics  — MUST come before /{incident_id} to avoid shadowing
# ------------------------------------------------------------------ #

@router.get(
    "/statistics",
    response_model=IncidentStats,
    summary="Real incident statistics (any authenticated user)",
)
def incident_statistics(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.get_incident_stats(db)


# ------------------------------------------------------------------ #
# Create
# ------------------------------------------------------------------ #

@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a new incident (it_engineer / admin / manager)",
)
def create_incident(
    payload:      IncidentCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_WRITE_ROLES)),
):
    return service.create_incident(db, payload, reporter_id=current_user.id)


# ------------------------------------------------------------------ #
# List  (filters via query params)
# ------------------------------------------------------------------ #

@router.get(
    "",
    response_model=List[IncidentListItem],
    summary="List incidents with optional filters (any authenticated user)",
)
def list_incidents(
    status_filter:   Optional[str] = Query(None, alias="status",
                         description="Filter by status: open|investigating|resolved|closed"),
    severity_filter: Optional[str] = Query(None, alias="severity",
                         description="Filter by severity: low|medium|high|critical"),
    assigned_to:     Optional[int] = Query(None, description="Filter by assignee user ID"),
    reported_by:     Optional[int] = Query(None, description="Filter by reporter user ID"),
    affected_system: Optional[str] = Query(None, description="Partial match on affected_system"),
    search:          Optional[str] = Query(None, description="Search title/description"),
    skip:            int           = Query(0,  ge=0),
    limit:           int           = Query(50, ge=1, le=200),
    db:              Session       = Depends(get_db),
    current_user:    User          = Depends(get_current_user),
):
    return service.list_incidents(
        db,
        status_filter=status_filter,
        severity_filter=severity_filter,
        assigned_to=assigned_to,
        reported_by=reported_by,
        affected_system=affected_system,
        search=search,
        skip=skip,
        limit=limit,
    )


# ------------------------------------------------------------------ #
# Get single
# ------------------------------------------------------------------ #

@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Get a single incident (any authenticated user)",
)
def get_incident(
    incident_id:  int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.get_incident(db, incident_id)


# ------------------------------------------------------------------ #
# Update (general field edit)
# ------------------------------------------------------------------ #

@router.put(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Update incident fields (it_engineer / admin / manager)",
)
def update_incident(
    incident_id:  int,
    payload:      IncidentUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_WRITE_ROLES)),
):
    return service.update_incident(db, incident_id, payload, actor_id=current_user.id)


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@router.delete(
    "/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an incident permanently (admin / manager)",
)
def delete_incident(
    incident_id:  int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_ASSIGN_ROLES)),
):
    service.delete_incident(db, incident_id)


# ------------------------------------------------------------------ #
# Status transition
# ------------------------------------------------------------------ #

@router.put(
    "/{incident_id}/status",
    response_model=IncidentResponse,
    summary="Change incident status (it_engineer / admin / manager)",
)
def update_status(
    incident_id:  int,
    payload:      IncidentStatusUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_WRITE_ROLES)),
):
    return service.update_incident_status(
        db, incident_id, payload.status,
        actor_id=current_user.id, notes=payload.notes,
    )


# ------------------------------------------------------------------ #
# Assign
# ------------------------------------------------------------------ #

@router.put(
    "/{incident_id}/assign",
    response_model=IncidentResponse,
    summary="Assign incident to a user (admin / manager)",
)
def assign_incident(
    incident_id:  int,
    payload:      IncidentAssign,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_ASSIGN_ROLES)),
):
    return service.assign_incident(
        db, incident_id, payload.assigned_to,
        actor_id=current_user.id, notes=payload.notes,
    )


# ------------------------------------------------------------------ #
# Resolve
# ------------------------------------------------------------------ #

@router.put(
    "/{incident_id}/resolve",
    response_model=IncidentResponse,
    summary="Resolve an incident with root cause (it_engineer / admin / manager)",
)
def resolve_incident(
    incident_id:  int,
    payload:      IncidentResolve,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_WRITE_ROLES)),
):
    return service.resolve_incident(
        db, incident_id, payload.root_cause,
        actor_id=current_user.id, notes=payload.notes,
    )


# ------------------------------------------------------------------ #
# Close
# ------------------------------------------------------------------ #

@router.put(
    "/{incident_id}/close",
    response_model=IncidentResponse,
    summary="Close an incident (it_engineer / admin / manager)",
)
def close_incident(
    incident_id:  int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_WRITE_ROLES)),
    notes: Optional[str] = Query(None, description="Optional closing note"),
):
    return service.close_incident(
        db, incident_id, actor_id=current_user.id, notes=notes,
    )


# ------------------------------------------------------------------ #
# Timeline / audit
# ------------------------------------------------------------------ #

@router.get(
    "/{incident_id}/timeline",
    response_model=List[TimelineEntryResponse],
    summary="Get audit trail for an incident (any authenticated user)",
)
def get_timeline(
    incident_id:  int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.get_incident_timeline(db, incident_id)


# ------------------------------------------------------------------ #
# AI Triage — run
# ------------------------------------------------------------------ #

@router.post(
    "/{incident_id}/triage",
    response_model=AITriageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run Gemini AI triage on an incident (it_engineer / admin / manager)",
)
def run_triage(
    incident_id:  int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(_WRITE_ROLES)),
):
    return service.run_ai_triage(db, incident_id)


# ------------------------------------------------------------------ #
# AI Triage — get latest
# ------------------------------------------------------------------ #

@router.get(
    "/{incident_id}/triage",
    response_model=AITriageResponse,
    summary="Get the latest AI triage result for an incident (any authenticated user)",
)
def get_triage(
    incident_id:  int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.get_latest_triage(db, incident_id)
