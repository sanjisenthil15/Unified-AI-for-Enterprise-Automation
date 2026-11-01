"""
modules/escalations/router.py

Endpoints:
    GET  /escalations        — escalation history (Admin / HR Manager)
    POST /escalations/run    — run the sweep now, ignoring the throttle (Admin)
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import require_roles
from core.permissions import ROLE_ADMIN, ROLE_HR
from models.user import User
from modules.escalations import service

router = APIRouter(prefix="/escalations", tags=["Escalations"])


class EscalationResponse(BaseModel):
    id: int
    rule: str
    entity_type: str
    entity_id: int
    status: str
    summary: str
    recipient_count: int
    triggered_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


@router.get("", response_model=List[EscalationResponse], summary="Escalation history (Admin / HR Manager)")
def list_escalations(
    status: Optional[str] = Query(None, pattern="^(open|resolved)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([ROLE_ADMIN, ROLE_HR])),
):
    return service.list_escalations(db, status, limit)


@router.post("/run", summary="Run the escalation sweep now (Admin)")
def run_sweep(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([ROLE_ADMIN])),
):
    result = service.run_sweep_now(db, force=True)
    if result is None:
        return {"skipped": True, "reason": "Another sweep is running right now."}
    return {"skipped": False, **result}
