"""
modules/audit/router.py

Read-only access to the audit trail — Admin only. There are no write,
update or delete endpoints: rows are only ever created by core/audit.py
inside the transaction they describe, and the table itself rejects
UPDATE / DELETE / TRUNCATE.

Endpoints:
    GET /audit-logs          — filterable, newest first, keyset-paged by before_id
"""

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import require_roles
from core.permissions import ROLE_ADMIN
from models.audit_log import AuditLog
from models.user import User

router = APIRouter(prefix="/audit-logs", tags=["Audit Log"])


class AuditLogResponse(BaseModel):
    id: int
    occurred_at: datetime
    actor_user_id: Optional[int] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    before: Optional[Any] = None
    after: Optional[Any] = None
    correlation_id: Optional[str] = None


class AuditLogPage(BaseModel):
    items: List[AuditLogResponse]
    next_before_id: Optional[int] = None


@router.get("", response_model=AuditLogPage, summary="Audit trail (Admin only)")
def list_audit_logs(
    entity_type: Optional[str] = Query(None, max_length=50),
    entity_id: Optional[str] = Query(None, max_length=64),
    action: Optional[str] = Query(None, max_length=80, description="Exact action, or a prefix ending in '.' e.g. 'leave_request.'"),
    actor_user_id: Optional[int] = Query(None, ge=1),
    correlation_id: Optional[str] = Query(None, max_length=64),
    occurred_from: Optional[datetime] = None,
    occurred_to: Optional[datetime] = None,
    before_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([ROLE_ADMIN])),
):
    query = db.query(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.actor_user_id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        if action.endswith("."):
            query = query.filter(AuditLog.action.startswith(action, autoescape=True))
        else:
            query = query.filter(AuditLog.action == action)
    if actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if correlation_id:
        query = query.filter(AuditLog.correlation_id == correlation_id)
    if occurred_from is not None:
        query = query.filter(AuditLog.occurred_at >= occurred_from)
    if occurred_to is not None:
        query = query.filter(AuditLog.occurred_at <= occurred_to)
    if before_id is not None:
        query = query.filter(AuditLog.id < before_id)

    rows = query.order_by(AuditLog.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        AuditLogResponse(
            id=log.id, occurred_at=log.occurred_at, actor_user_id=log.actor_user_id, actor_name=actor_name,
            actor_role=log.actor_role, action=log.action, entity_type=log.entity_type, entity_id=log.entity_id,
            before=log.before, after=log.after, correlation_id=log.correlation_id,
        )
        for log, actor_name in rows
    ]
    return AuditLogPage(items=items, next_before_id=items[-1].id if has_more and items else None)
