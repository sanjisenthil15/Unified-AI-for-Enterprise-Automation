"""
modules/notifications/router.py

FastAPI router for the Notifications module.

Endpoints:
    GET  /notifications/me             — the caller's own notifications (any user)
    POST /notifications/{id}/read      — mark one read (any user, own only)
    POST /notifications/read-all       — mark all read (any user)
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_user
from models.user import User

from modules.notifications.schemas import NotificationResponse
from modules.notifications import service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/me", response_model=List[NotificationResponse], summary="The caller's own notifications")
def list_my_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_my_notifications(db, current_user.id, unread_only=unread_only)


@router.post("/{notification_id}/read", response_model=NotificationResponse, summary="Mark one notification read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.mark_read(db, current_user.id, notification_id)


@router.post("/read-all", summary="Mark all of the caller's notifications read")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = service.mark_all_read(db, current_user.id)
    return {"updated": count}
