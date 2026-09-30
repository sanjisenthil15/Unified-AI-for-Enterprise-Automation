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
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


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
    assigned_to: int = Field(..., description="User ID to assign this incident to")
    notes:       Optional[str] = None


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
