"""
modules/notifications/service.py

Business logic for the Notifications module.

create_notification() is called directly by other modules' service
functions (Sprints on task assignment, Manager Chat on new message) right
after the relevant write — no event bus, matching how lightly coupled
this app's modules already are.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from models.notification import Notification


def create_notification(db: Session, user_id: int, type: str, message: str, link: Optional[str] = None) -> Notification:
    notification = Notification(user_id=user_id, type=type, message=message, link=link)
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def list_my_notifications(db: Session, user_id: int, *, unread_only: bool = False) -> list[Notification]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    return query.order_by(Notification.created_at.desc()).limit(100).all()


def mark_read(db: Session, user_id: int, notification_id: int) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == user_id)
        .first()
    )
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Notification id={notification_id} not found.")
    if notification.read_at is None:
        notification.read_at = func.now()
        db.commit()
        db.refresh(notification)
    return notification


def mark_all_read(db: Session, user_id: int) -> int:
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
        .update({Notification.read_at: func.now()}, synchronize_session=False)
    )
    db.commit()
    return updated
