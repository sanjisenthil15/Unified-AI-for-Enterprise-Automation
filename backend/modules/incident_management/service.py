"""
modules/incident_management/service.py

Business logic for the Incident Management module.

Functions:
    get_incident_or_404         — shared fetch helper
    create_incident             — POST /incidents
    list_incidents              — GET  /incidents (with filters + pagination)
    get_incident                — GET  /incidents/{id}
    update_incident             — PUT  /incidents/{id}
    update_incident_status      — PUT  /incidents/{id}/status
    assign_incident             — PUT  /incidents/{id}/assign
    resolve_incident            — PUT  /incidents/{id}/resolve
    close_incident              — PUT  /incidents/{id}/close
    delete_incident             — DELETE /incidents/{id}
    get_incident_timeline       — GET  /incidents/{id}/timeline
    run_ai_triage               — POST /incidents/{id}/triage
    get_latest_triage           — GET  /incidents/{id}/triage
    get_incident_stats          — GET  /incidents/statistics

Timeline helper:
    _add_timeline               — internal, records every audit event
"""

import json
import re
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from config.settings import settings
from models.incident import Incident, IncidentAITriage, IncidentTimeline
from models.user import User

# Import google-genai at module level. Using try/except so the server
# starts even if the package is missing (run_ai_triage will 503 instead of crash).
try:
    from google import genai as _genai
except ImportError:
    _genai = None  # type: ignore[assignment]


# ------------------------------------------------------------------ #
# Valid status transitions
# ------------------------------------------------------------------ #

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open":          {"investigating", "resolved", "closed"},
    "investigating": {"resolved", "closed", "open"},
    "resolved":      {"closed", "open"},          # allow reopen
    "closed":        {"open"},                     # allow reopen
}


# ------------------------------------------------------------------ #
# Shared fetch helper
# ------------------------------------------------------------------ #

def get_incident_or_404(db: Session, incident_id: int) -> Incident:
    """Return the Incident or raise HTTP 404."""
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident id={incident_id} not found.",
        )
    return incident


# ------------------------------------------------------------------ #
# Timeline helper
# ------------------------------------------------------------------ #

def _add_timeline(
    db: Session,
    incident_id: int,
    action: str,
    actor_id: Optional[int],   # None = AI action
    notes: Optional[str] = None,
) -> IncidentTimeline:
    entry = IncidentTimeline(
        incident_id=incident_id,
        actor_id=actor_id,
        action=action,
        notes=notes,
    )
    db.add(entry)
    # Caller is responsible for db.commit()
    return entry


# ------------------------------------------------------------------ #
# Create
# ------------------------------------------------------------------ #

def create_incident(db: Session, payload, reporter_id: int) -> Incident:
    """Create a new incident and record the creation in timeline."""
    incident = Incident(
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        affected_system=payload.affected_system,
        status="open",
        reported_by=reporter_id,
    )
    db.add(incident)
    db.flush()   # get incident.id before timeline insert

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_created",
        actor_id=reporter_id,
        notes=f"Incident created with severity '{payload.severity}'.",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# List (with filters and simple pagination)
# ------------------------------------------------------------------ #

def list_incidents(
    db: Session,
    status_filter: Optional[str]  = None,
    severity_filter: Optional[str] = None,
    assigned_to: Optional[int]    = None,
    reported_by: Optional[int]    = None,
    affected_system: Optional[str] = None,
    search: Optional[str]         = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Incident]:
    q = db.query(Incident)

    if status_filter:
        q = q.filter(Incident.status == status_filter)
    if severity_filter:
        q = q.filter(Incident.severity == severity_filter)
    if assigned_to is not None:
        q = q.filter(Incident.assigned_to == assigned_to)
    if reported_by is not None:
        q = q.filter(Incident.reported_by == reported_by)
    if affected_system:
        q = q.filter(Incident.affected_system.ilike(f"%{affected_system}%"))
    if search:
        term = f"%{search}%"
        q = q.filter(
            Incident.title.ilike(term) | Incident.description.ilike(term)
        )

    return (
        q.order_by(Incident.created_at.desc())
         .offset(skip)
         .limit(limit)
         .all()
    )


# ------------------------------------------------------------------ #
# Get single
# ------------------------------------------------------------------ #

def get_incident(db: Session, incident_id: int) -> Incident:
    return get_incident_or_404(db, incident_id)


# ------------------------------------------------------------------ #
# Update (general field edit)
# ------------------------------------------------------------------ #

def update_incident(db: Session, incident_id: int, payload, actor_id: int) -> Incident:
    incident = get_incident_or_404(db, incident_id)
    changes  = []

    if payload.title is not None and payload.title != incident.title:
        changes.append(f"title changed")
        incident.title = payload.title

    if payload.description is not None and payload.description != incident.description:
        changes.append("description updated")
        incident.description = payload.description

    if payload.severity is not None and payload.severity != incident.severity:
        changes.append(f"severity changed from '{incident.severity}' to '{payload.severity}'")
        incident.severity = payload.severity

    if payload.affected_system is not None and payload.affected_system != incident.affected_system:
        changes.append(f"affected_system updated to '{payload.affected_system}'")
        incident.affected_system = payload.affected_system

    if payload.root_cause is not None and payload.root_cause != incident.root_cause:
        changes.append("root_cause updated")
        incident.root_cause = payload.root_cause

    if changes:
        _add_timeline(
            db,
            incident_id=incident.id,
            action="incident_updated",
            actor_id=actor_id,
            notes="; ".join(changes),
        )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Status update
# ------------------------------------------------------------------ #

def update_incident_status(
    db: Session, incident_id: int, new_status: str,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)
    old_status = incident.status

    if new_status == old_status:
        return incident   # no-op

    allowed = _ALLOWED_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition: '{old_status}' → '{new_status}'. "
                f"Allowed from '{old_status}': {sorted(allowed)}."
            ),
        )

    incident.status = new_status
    _add_timeline(
        db,
        incident_id=incident.id,
        action="status_changed",
        actor_id=actor_id,
        notes=notes or f"Status changed from '{old_status}' to '{new_status}'.",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Assign
# ------------------------------------------------------------------ #

def assign_incident(
    db: Session, incident_id: int, assigned_to_user_id: int,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)

    # Validate the target user exists
    target_user = db.query(User).filter(
        User.id == assigned_to_user_id,
        User.deleted_at.is_(None),
        User.is_active == True,
    ).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User id={assigned_to_user_id} not found or inactive.",
        )

    old_assignee = incident.assigned_to
    incident.assigned_to = assigned_to_user_id

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_assigned",
        actor_id=actor_id,
        notes=notes or (
            f"Assigned to {target_user.full_name} (id={assigned_to_user_id})"
            + (f", previously {old_assignee}" if old_assignee else "")
        ),
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Resolve
# ------------------------------------------------------------------ #

def resolve_incident(
    db: Session, incident_id: int, root_cause: str,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)

    if incident.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot resolve a closed incident. Reopen it first.",
        )
    if incident.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident is already resolved.",
        )

    incident.status      = "resolved"
    incident.root_cause  = root_cause
    incident.resolved_at = datetime.utcnow()

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_resolved",
        actor_id=actor_id,
        notes=notes or f"Resolved. Root cause: {root_cause[:200]}",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Close
# ------------------------------------------------------------------ #

def close_incident(
    db: Session, incident_id: int,
    actor_id: int, notes: Optional[str] = None,
) -> Incident:
    incident = get_incident_or_404(db, incident_id)

    if incident.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident is already closed.",
        )
    if incident.status not in ("resolved", "investigating", "open"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot close incident with status '{incident.status}'.",
        )

    incident.status = "closed"
    # Set resolved_at if not already set (e.g. closed without formal resolution)
    if not incident.resolved_at:
        incident.resolved_at = datetime.utcnow()

    _add_timeline(
        db,
        incident_id=incident.id,
        action="incident_closed",
        actor_id=actor_id,
        notes=notes or "Incident closed.",
    )

    db.commit()
    db.refresh(incident)
    return incident


# ------------------------------------------------------------------ #
# Delete (hard delete — Incident model has no deleted_at)
# ------------------------------------------------------------------ #

def delete_incident(db: Session, incident_id: int) -> None:
    """Hard delete. Timeline + triage rows are removed by CASCADE."""
    incident = get_incident_or_404(db, incident_id)
    db.delete(incident)
    db.commit()


# ------------------------------------------------------------------ #
# Timeline
# ------------------------------------------------------------------ #

def get_incident_timeline(db: Session, incident_id: int) -> List[IncidentTimeline]:
    get_incident_or_404(db, incident_id)   # raises 404 if missing
    return (
        db.query(IncidentTimeline)
        .filter(IncidentTimeline.incident_id == incident_id)
        .order_by(IncidentTimeline.created_at.asc())
        .all()
    )


# ------------------------------------------------------------------ #
# AI Triage
# ------------------------------------------------------------------ #

_TRIAGE_PROMPT_TEMPLATE = """\
You are an expert IT incident triage assistant.

Analyze the following incident and respond with ONLY a valid JSON object.
Do not include markdown, code fences, or any text outside the JSON.

Incident Title: {title}
Affected System: {affected_system}
Description:
{description}

Return this exact JSON structure:
{{
  "suggested_severity": "low|medium|high|critical",
  "suggested_owner": "Team or role name best suited to handle this, or null",
  "reasoning": "Concise explanation of your severity assessment and owner recommendation",
  "confidence": <number between 0.0 and 100.0>
}}

Rules:
- suggested_severity must be exactly one of: low, medium, high, critical
- confidence must be a number (not a string)
- Do not invent details not present in the incident description
- reasoning must be under 500 characters
"""


def run_ai_triage(db: Session, incident_id: int) -> IncidentAITriage:
    """
    Send incident details to Gemini, parse the structured JSON response,
    store in incident_ai_triage, and record the action in timeline.

    Raises HTTPException on configuration, API, or parse errors.
    """
    incident = get_incident_or_404(db, incident_id)

    # ── Check API key ─────────────────────────────────────────────
    api_key = settings.GEMINI_API_KEY
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured.",
        )

    # ── Build prompt ──────────────────────────────────────────────
    prompt = _TRIAGE_PROMPT_TEMPLATE.format(
        title=incident.title,
        affected_system=incident.affected_system or "Not specified",
        description=incident.description,
    )

    # ── Call Gemini ──────────────────────────────────────────────
    if _genai is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini SDK (google-genai) is not installed.",
        )
    try:
        client   = _genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        raw_text = response.text.strip()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {exc}",
        )

    # ── Parse JSON response ───────────────────────────────────────
    # Strip markdown fences if Gemini adds them despite instructions
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.DOTALL).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini returned non-JSON response: {raw_text[:300]}",
        )

    # ── Validate required fields ──────────────────────────────────
    valid_severities = {"low", "medium", "high", "critical"}
    suggested_severity = str(data.get("suggested_severity", "medium")).lower().strip()
    if suggested_severity not in valid_severities:
        suggested_severity = "medium"   # safe fallback

    suggested_owner = data.get("suggested_owner")
    if suggested_owner:
        suggested_owner = str(suggested_owner)[:120]

    reasoning = str(data.get("reasoning", "No reasoning provided."))[:2000]

    raw_confidence = data.get("confidence")
    try:
        confidence = float(raw_confidence)
        confidence = max(0.0, min(100.0, confidence))   # clamp to valid range
    except (TypeError, ValueError):
        confidence = None

    # ── Persist triage result ─────────────────────────────────────
    triage = IncidentAITriage(
        incident_id=incident_id,
        suggested_severity=suggested_severity,
        suggested_owner=suggested_owner,
        reasoning=reasoning,
        confidence=confidence,
        ai_model="gemini-3.6-flash",
    )
    db.add(triage)

    # ── Timeline entry (actor_id=None → AI action) ────────────────
    _add_timeline(
        db,
        incident_id=incident_id,
        action="ai_triage_completed",
        actor_id=None,
        notes=(
            f"AI suggested severity: '{suggested_severity}', "
            f"owner: '{suggested_owner or 'N/A'}', "
            f"confidence: {confidence:.1f}%" if confidence is not None
            else f"AI suggested severity: '{suggested_severity}'."
        ),
    )

    db.commit()
    db.refresh(triage)
    return triage


def get_latest_triage(db: Session, incident_id: int) -> IncidentAITriage:
    """Return the most recent AI triage for an incident, or 404."""
    get_incident_or_404(db, incident_id)
    triage = (
        db.query(IncidentAITriage)
        .filter(IncidentAITriage.incident_id == incident_id)
        .order_by(IncidentAITriage.generated_at.desc())
        .first()
    )
    if not triage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI triage found for incident id={incident_id}.",
        )
    return triage


# ------------------------------------------------------------------ #
# Statistics
# ------------------------------------------------------------------ #

def get_incident_stats(db: Session) -> dict:
    """Compute real statistics from the database — no hardcoded values."""

    total         = db.query(Incident).count()
    open_count    = db.query(Incident).filter(Incident.status == "open").count()
    investigating = db.query(Incident).filter(Incident.status == "investigating").count()
    resolved      = db.query(Incident).filter(Incident.status == "resolved").count()
    closed        = db.query(Incident).filter(Incident.status == "closed").count()

    sev_low      = db.query(Incident).filter(Incident.severity == "low").count()
    sev_medium   = db.query(Incident).filter(Incident.severity == "medium").count()
    sev_high     = db.query(Incident).filter(Incident.severity == "high").count()
    sev_critical = db.query(Incident).filter(Incident.severity == "critical").count()

    # Average resolution time in minutes (only for incidents with resolved_at set)
    avg_minutes: Optional[float] = None
    rows = (
        db.query(Incident.created_at, Incident.resolved_at)
        .filter(Incident.resolved_at.isnot(None))
        .all()
    )
    if rows:
        total_seconds = sum(
            (
                (row.resolved_at.replace(tzinfo=None) if row.resolved_at else None) -
                (row.created_at.replace(tzinfo=None)  if row.created_at  else None)
            ).total_seconds()
            for row in rows
            if row.resolved_at and row.created_at
        )
        avg_minutes = round(total_seconds / 60 / len(rows), 2)

    return {
        "total":         total,
        "open":          open_count,
        "investigating": investigating,
        "resolved":      resolved,
        "closed":        closed,
        "severity_low":      sev_low,
        "severity_medium":   sev_medium,
        "severity_high":     sev_high,
        "severity_critical": sev_critical,
        "avg_resolution_minutes": avg_minutes,
    }
