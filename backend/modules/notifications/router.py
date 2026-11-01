"""
modules/notifications/router.py

FastAPI router for the Notifications module.

Endpoints:
    GET  /notifications/me             — the caller's own notifications (any user);
                                         optional category / unread_only / paging
    GET  /notifications/unread-count   — unread totals, overall and per category
    POST /notifications/{id}/read      — mark one read (any user, own only)
    POST /notifications/read-all       — mark all read (optionally one category)

GET /notifications/me is what every signed-in browser polls, so it also
queues the throttled escalation sweep as a background task (there is no
scheduler process — see modules/escalations/service.py).
"""

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_user
from models.notification import NOTIFICATION_CATEGORIES
from models.user import User

from modules.escalations.service import run_sweep_if_due
from modules.notifications.schemas import NotificationResponse, UnreadCountResponse
from modules.notifications import service

router = APIRouter(prefix="/notifications", tags=["Notifications"])

_CATEGORY_PATTERN = "^(" + "|".join(NOTIFICATION_CATEGORIES) + ")$"


@router.get("/me", response_model=List[NotificationResponse], summary="The caller's own notifications")
def list_my_notifications(
    background_tasks: BackgroundTasks,
    unread_only: bool = False,
    category: Optional[str] = Query(None, pattern=_CATEGORY_PATTERN),
    limit: int = Query(100, ge=1, le=200),
    before_id: Optional[int] = Query(None, ge=1, description="Return only notifications older than this id (paging)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    background_tasks.add_task(run_sweep_if_due)
    return service.list_my_notifications(
        db, current_user.id, unread_only=unread_only, category=category, limit=limit, before_id=before_id,
    )


@router.get("/unread-count", response_model=UnreadCountResponse, summary="Unread notification counts")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.unread_counts(db, current_user.id)


@router.post("/{notification_id}/read", response_model=NotificationResponse, summary="Mark one notification read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.mark_read(db, current_user.id, notification_id)


@router.post("/read-all", summary="Mark all of the caller's notifications read")
def mark_all_read(
    category: Optional[str] = Query(None, pattern=_CATEGORY_PATTERN),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = service.mark_all_read(db, current_user.id, category=category)
    return {"updated": count}
