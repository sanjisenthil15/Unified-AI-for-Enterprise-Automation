"""
modules/incident_management/schemas.py

Pydantic v2 schemas for the Incident Management module.

Schemas:
    IncidentCreate          — POST /incidents
    IncidentUpdate          — PUT  /incidents/{id}
    IncidentStatusUpdate    — PUT  /incidents/{id}/status
    IncidentAssign          — PUT  /incidents/{id}/assign
    IncidentResolve         — PUT  /incidents/{id}/resolve
    IncidentResponse        — full incident record returned to clients
    IncidentListItem        — lightweight row for list views
    TimelineEntryResponse   — single timeline entry
    AITriageResponse        — AI triage result
    IncidentStats           — GET  /incidents/statistics
"""

from datetime import datetime
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------ #
# Shared literals — must match DB ENUM values exactly
# ------------------------------------------------------------------ #

SeverityEnum = Literal["low", "medium", "high", "critical"]
StatusEnum   = Literal["open", "investigating", "resolved", "closed"]


# ------------------------------------------------------------------ #
# Nested user info (embedded in responses)
# ------------------------------------------------------------------ #

class UserBrief(BaseModel):
    id:        int
    full_name: str
    email:     str
    role:      Optional[str] = None
    team_name: Optional[str] = None

    @field_validator("role", mode="before")
    @classmethod
    def _extract_role(cls, v):
        if hasattr(v, "name"):
            return v.name
        return str(v) if v is not None else None

    model_config = {"from_attributes": True}

# ------------------------------------------------------------------ #
# Team & Member schemas for AI assignment
# ------------------------------------------------------------------ #

class IncidentTeamMember(BaseModel):
    user_id:     int
    employee_id: int
    full_name:   str
    email:       str
    job_title:   Optional[str] = None
    role:        Optional[str] = None
    status:      str = "active"

    model_config = {"from_attributes": True}


class IncidentTeamResponse(BaseModel):
    id:           str
    team_id:      int
    team_type:    str
    name:         str
    description:  Optional[str] = None
    member_count: int
    members:      Optional[List[IncidentTeamMember]] = None

    model_config = {"from_attributes": True}



# ------------------------------------------------------------------ #
# Request schemas
# ------------------------------------------------------------------ #

class IncidentCreate(BaseModel):
    title:           str            = Field(..., min_length=3, max_length=255)
    description:     str            = Field(..., min_length=10)
    severity:        SeverityEnum   = "medium"
    affected_system: Optional[str]  = Field(None, max_length=120)


class IncidentUpdate(BaseModel):
    """Partial update — all fields optional."""
    title:           Optional[str]          = Field(None, min_length=3, max_length=255)
    description:     Optional[str]          = Field(None, min_length=10)
    severity:        Optional[SeverityEnum] = None
    affected_system: Optional[str]          = Field(None, max_length=120)
    root_cause:      Optional[str]          = None


class IncidentStatusUpdate(BaseModel):
    status: StatusEnum
    notes:  Optional[str] = Field(None, description="Optional comment about this status change")


class IncidentAssign(BaseModel):
    assigned_to:         int                       = Field(..., description="User ID to assign this incident to")
    team_id:             Optional[Union[str, int]] = Field(None, description="Selected team ID (project or department)")
    team_name:           Optional[str]             = Field(None, description="Selected team name")
    ai_recommended_team: Optional[str]             = Field(None, description="Original AI recommended team if any")
    notes:               Optional[str]             = None


class IncidentResolve(BaseModel):
    root_cause: str  = Field(..., min_length=5, description="Root cause of the incident")
    notes:      Optional[str] = None


# ------------------------------------------------------------------ #
# Response schemas
# ------------------------------------------------------------------ #

class IncidentResponse(BaseModel):
    id:              int
    title:           str
    description:     str
    severity:        str
    status:          str
    affected_system: Optional[str]
    root_cause:      Optional[str]
    reported_by:     int
    assigned_to:     Optional[int]
    reporter:        Optional[UserBrief]  = None
    assignee:        Optional[UserBrief]  = None
    team_name:       Optional[str]        = None
    ai_triage:       Optional["AITriageResponse"] = None
    resolved_at:     Optional[datetime]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}


class IncidentListItem(BaseModel):
    """Lightweight row — avoids loading all relationships for large lists."""
    id:              int
    title:           str
    severity:        str
    status:          str
    affected_system: Optional[str]
    reported_by:     int
    assigned_to:     Optional[int]
    team_name:       Optional[str]        = None
    assignee_name:   Optional[str]        = None
    resolved_at:     Optional[datetime]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# Timeline
# ------------------------------------------------------------------ #

class TimelineEntryResponse(BaseModel):
    id:          int
    incident_id: int
    actor_id:    Optional[int]       # NULL = AI action
    actor:       Optional[UserBrief] = None
    action:      str
    notes:       Optional[str]
    created_at:  datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# AI Triage
# ------------------------------------------------------------------ #

class AITriageResponse(BaseModel):
    id:                 int
    incident_id:        int
    suggested_severity: str
    suggested_owner:    Optional[str]
    reasoning:          str
    confidence:         Optional[float]
    ai_model:           str
    generated_at:       datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# Statistics
# ------------------------------------------------------------------ #

class IncidentStats(BaseModel):
    total:          int
    open:           int
    investigating:  int
    resolved:       int
    closed:         int
    severity_low:      int
    severity_medium:   int
    severity_high:     int
    severity_critical: int
    avg_resolution_minutes: Optional[float]  # None if no resolved incidents yet
