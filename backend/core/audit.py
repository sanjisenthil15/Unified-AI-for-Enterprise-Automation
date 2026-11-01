"""
core/audit.py

Audit trail plumbing (Phase 4.5).

How a row gets into audit_logs:
  1. AuditContextMiddleware gives every HTTP request a correlation id
     (the caller's X-Request-ID if it's sane, otherwise a new one — echoed
     back in the response) and an empty actor slot.
  2. core/dependencies._resolve_user fills the actor slot with the
     authenticated user (set_actor).
  3. An after_flush listener on SessionLocal turns every insert / update /
     delete of an audited model into an audit row, written on the same
     connection inside the same transaction — so if the change rolls back,
     so does its audit row, and nothing can be audited that didn't happen.
  4. Events that aren't a plain row change (login, password change/reset)
     are added explicitly with record_event().

Only allow-listed columns are ever copied into before/after: password
hashes, token versions, phone numbers and free-text personal notes (e.g.
a leave request's reason, which can carry medical detail) never reach
the audit table.

The request context is a ContextVar holding a *mutable dict*: FastAPI
runs sync dependencies in a worker thread with a copy of the context, so
re-binding the variable there would be invisible to the endpoint — but
both copies point at the same dict, so filling it in place works.
"""

import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql import ClauseElement

from models.audit_log import AuditLog

CORRELATION_HEADER = "x-request-id"
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_request_ctx: ContextVar[Optional[dict]] = ContextVar("audit_request_ctx", default=None)


# ------------------------------------------------------------------ #
# Request context
# ------------------------------------------------------------------ #

def _new_context(correlation_id: Optional[str] = None, actor_user_id=None, actor_role=None) -> dict:
    return {
        "correlation_id": correlation_id or uuid.uuid4().hex,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
    }


def current_context() -> dict:
    ctx = _request_ctx.get()
    return ctx if ctx is not None else {"correlation_id": None, "actor_user_id": None, "actor_role": None}


def set_actor(user) -> None:
    """Record the authenticated user as the actor for the current request."""
    ctx = _request_ctx.get()
    if ctx is None or user is None:
        return
    ctx["actor_user_id"] = user.id
    role = getattr(user, "role", None)
    ctx["actor_role"] = getattr(role, "name", None)


@contextmanager
def system_context(job_name: str):
    """Attribute changes made inside the block to an automated job rather
    than to whichever request happened to trigger it."""
    token = _request_ctx.set(_new_context(actor_role=f"system:{job_name}"))
    try:
        yield
    finally:
        _request_ctx.reset(token)


class AuditContextMiddleware:
    """Pure-ASGI middleware: binds a fresh audit context per HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for name, value in scope.get("headers", []):
            if name == CORRELATION_HEADER.encode():
                incoming = value.decode("latin-1").strip()
                break
        correlation_id = incoming if incoming and _SAFE_CORRELATION_ID.match(incoming) else uuid.uuid4().hex

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((CORRELATION_HEADER.encode(), correlation_id.encode()))
                message["headers"] = headers
            await send(message)

        token = _request_ctx.set(_new_context(correlation_id))
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _request_ctx.reset(token)


# ------------------------------------------------------------------ #
# What gets audited
# ------------------------------------------------------------------ #

# class name -> (entity_type, allow-listed columns). Imported lazily by
# name so this module doesn't import every model at load time.
AUDITED_MODELS: dict[str, tuple[str, tuple[str, ...]]] = {
    "User": ("user", (
        "role_id", "is_active", "must_change_password", "password_changed_at",
        "password_reset_by_id", "password_reset_at", "deleted_at",
    )),
    "Employee": ("employee", (
        "user_id", "department_id", "project_id", "employee_code", "job_title",
        "employment_type", "status", "deleted_at",
    )),
    "Project": ("project", (
        "name", "status", "start_date", "deadline", "team_lead_id", "manager_user_id",
        "completed_at", "cancelled_at", "archived_at",
    )),
    "LeaveRequest": ("leave_request", (
        "employee_id", "leave_type", "start_date", "end_date", "working_days", "status",
        "reviewed_by_id", "reviewed_at", "cancelled_at",
    )),
    "MeetingActionItem": ("meeting_action_item", (
        "meeting_id", "assigned_to_user_id", "assigned_to_employee_id", "due_date", "priority",
        "status", "review_status", "reviewed_by_id", "reviewed_at", "is_legacy_conversion",
        "converted_sprint_task_id",
    )),
    "Escalation": ("escalation", (
        "rule", "entity_type", "entity_id", "status", "recipient_count", "resolved_at",
    )),
}

_LABELS_KEY = "audit_action_labels"


def label(db: Session, obj, action: str) -> None:
    """Give the next audit row for `obj` a meaningful action name (e.g.
    'leave_request.approved') instead of the generic '<entity>.updated'."""
    db.info.setdefault(_LABELS_KEY, {})[id(obj)] = action


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ClauseElement):
        return "<set by database>"
    return str(value)


def _snapshot(state, columns) -> dict:
    # state.dict only holds already-loaded values — reading it never
    # triggers a lazy load in the middle of a flush.
    return {c: _json_safe(state.dict[c]) for c in columns if c in state.dict}


def _row(action, entity_type, entity_id, before, after) -> dict:
    ctx = current_context()
    return {
        "actor_user_id": ctx["actor_user_id"],
        "actor_role": ctx["actor_role"],
        "action": action,
        "entity_type": entity_type,
        "entity_id": None if entity_id is None else str(entity_id),
        "before": before,
        "after": after,
        "correlation_id": ctx["correlation_id"],
    }


def _audit_after_flush(session: Session, flush_context) -> None:
    # after_flush runs after the SQL but before SQLAlchemy resets history
    # and registers identities: session.new/dirty/deleted and attribute
    # history still describe this flush, and new rows' ids are already in
    # state.dict (every audited model's primary key is `id`).
    labels = session.info.get(_LABELS_KEY, {})
    rows = []

    for obj in session.new:
        spec = AUDITED_MODELS.get(type(obj).__name__)
        if spec is None:
            continue
        entity_type, columns = spec
        state = inspect(obj)
        rows.append(_row(
            labels.pop(id(obj), f"{entity_type}.created"), entity_type, state.dict.get("id"),
            None, _snapshot(state, columns),
        ))

    for obj in session.dirty:
        spec = AUDITED_MODELS.get(type(obj).__name__)
        if spec is None:
            continue
        entity_type, columns = spec
        state = inspect(obj)
        before, after = {}, {}
        for col in columns:
            hist = state.attrs[col].history
            if not hist.has_changes():
                continue
            old = hist.deleted[0] if hist.deleted else None
            new = hist.added[0] if hist.added else None
            if old == new:
                continue
            before[col] = _json_safe(old)
            after[col] = _json_safe(new)
        if not after:
            labels.pop(id(obj), None)
            continue
        rows.append(_row(
            labels.pop(id(obj), f"{entity_type}.updated"), entity_type, state.dict.get("id"),
            before, after,
        ))

    for obj in session.deleted:
        spec = AUDITED_MODELS.get(type(obj).__name__)
        if spec is None:
            continue
        entity_type, columns = spec
        state = inspect(obj)
        rows.append(_row(
            labels.pop(id(obj), f"{entity_type}.deleted"), entity_type, state.dict.get("id"),
            _snapshot(state, columns), None,
        ))

    if rows:
        session.connection().execute(AuditLog.__table__.insert(), rows)


def _discard_labels(session: Session, *args) -> None:
    session.info.pop(_LABELS_KEY, None)


def install(session_factory) -> None:
    """Attach the audit listener to the app's session factory (idempotent)."""
    if not event.contains(session_factory, "after_flush", _audit_after_flush):
        event.listen(session_factory, "after_flush", _audit_after_flush)
        # Labels only describe the transaction they were set in.
        event.listen(session_factory, "after_commit", _discard_labels)
        event.listen(session_factory, "after_rollback", _discard_labels)


# ------------------------------------------------------------------ #
# Explicit events
# ------------------------------------------------------------------ #

def record_event(
    db: Session,
    action: str,
    entity_type: str,
    entity_id=None,
    *,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    actor=None,
) -> None:
    """Queue an audit row for an event that isn't a plain row change. It is
    written with the caller's next commit — and discarded on rollback.
    Never pass secrets in before/after."""
    row = _row(action, entity_type, entity_id, before, after)
    if actor is not None:
        row["actor_user_id"] = actor.id
        row["actor_role"] = getattr(getattr(actor, "role", None), "name", None)
    db.add(AuditLog(**row))
