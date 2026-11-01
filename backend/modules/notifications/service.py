"""
modules/notifications/service.py

Business logic for the Notifications module — the app's single
notification system.

create_notification() is called directly by other modules' service
functions (Sprints on task assignment, Manager Chat on new message, Leave
on submission/decision, the escalation sweep) right after the relevant
write — no event bus, matching how lightly coupled this app's modules
already are.

Existing callers keep the original positional signature and its
commit-immediately behaviour. Newer callers that must stay atomic with
their own change pass commit=False, so the notification commits (or rolls
back) together with it, and may pass entity references, an explicit
category, and a dedupe_key (at most one notification per user per key —
safe to retry).
"""

from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from models.notification import NOTIFICATION_CATEGORIES, Notification

# Longest-prefix-first; anything unmatched is "general".
_CATEGORY_PREFIXES = (
    ("escalation", "escalation"),
    ("support_", "support"),
    ("leave_", "leave"),
    ("project_", "project"),
    ("task_", "sprint"),
    ("sprint_", "sprint"),
    ("meeting", "meeting"),
    ("chat_", "chat"),
    ("mention", "chat"),
)


def category_for_type(type: str) -> str:
    for prefix, category in _CATEGORY_PREFIXES:
        if type.startswith(prefix):
            return category
    return "general"


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    message: str,
    link: Optional[str] = None,
    *,
    category: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    commit: bool = True,
) -> Optional[Notification]:
    """Create one notification. Returns None when dedupe_key shows this
    user was already notified about it."""
    category = category or category_for_type(type)
    if category not in NOTIFICATION_CATEGORIES:
        raise ValueError(f"Unknown notification category {category!r}")

    if dedupe_key is not None:
        already = (
            db.query(Notification.id)
            .filter(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)
            .first()
        )
        if already is not None:
            return None

    notification = Notification(
        user_id=user_id, type=type, category=category, message=message[:255], link=link,
        entity_type=entity_type, entity_id=entity_id, dedupe_key=dedupe_key,
    )
    if dedupe_key is not None:
        # A concurrent producer may have inserted the same key since the
        # check above; the savepoint keeps that race from aborting the
        # caller's whole transaction.
        try:
            with db.begin_nested():
                db.add(notification)
        except IntegrityError:
            return None
    else:
        db.add(notification)

    if commit:
        db.commit()
        db.refresh(notification)
    return notification


def notify_users(
    db: Session,
    user_ids: Iterable[int],
    type: str,
    message: str,
    link: Optional[str] = None,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    dedupe_prefix: Optional[str] = None,
    category: Optional[str] = None,
) -> int:
    """Queue the same notification for several users inside the caller's
    transaction (never commits). Returns how many were actually created."""
    created = 0
    for uid in dict.fromkeys(user_ids):  # de-duplicate, keep order
        n = create_notification(
            db, uid, type, message, link,
            category=category, entity_type=entity_type, entity_id=entity_id,
            dedupe_key=f"{dedupe_prefix}:{uid}" if dedupe_prefix else None,
            commit=False,
        )
        if n is not None:
            created += 1
    return created


def list_my_notifications(
    db: Session,
    user_id: int,
    *,
    unread_only: bool = False,
    category: Optional[str] = None,
    limit: int = 100,
    before_id: Optional[int] = None,
) -> list[Notification]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    if category:
        query = query.filter(Notification.category == category)
    if before_id is not None:
        query = query.filter(Notification.id < before_id)
    return query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()


def unread_counts(db: Session, user_id: int) -> dict:
    rows = (
        db.query(Notification.category, func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
        .group_by(Notification.category)
        .all()
    )
    by_category = {category: count for category, count in rows}
    return {"total": sum(by_category.values()), "by_category": by_category}


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


def mark_all_read(db: Session, user_id: int, category: Optional[str] = None) -> int:
    query = db.query(Notification).filter(Notification.user_id == user_id, Notification.read_at.is_(None))
    if category:
        query = query.filter(Notification.category == category)
    updated = query.update({Notification.read_at: func.now()}, synchronize_session=False)
    db.commit()
    return updated
