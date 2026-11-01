"""
models/notification.py

SQLAlchemy ORM model for the `notifications` table.
The one per-user activity feed for the whole app (task assigned, chat
message, sprint created, leave decisions, escalations). Created directly
by other modules' service functions via
modules/notifications/service.create_notification — no event bus,
matching how lightly coupled this app's modules already are.

category groups types for filtering (sprint / meeting / chat / leave /
escalation / general); entity_type + entity_id point at the record the
notification is about; dedupe_key (unique per user) lets a caller that
might retry — e.g. the escalation sweep — insert a notification at most
once.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, Index, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base

NOTIFICATION_CATEGORIES = ("general", "sprint", "meeting", "chat", "leave", "project", "escalation", "support")


class Notification(Base):
    """A single notification for one user."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "uq_notifications_user_dedupe_key", "user_id", "dedupe_key",
            unique=True, postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String(50), nullable=False)
    category = Column(String(20), nullable=False, server_default="general", default="general", index=True)
    message = Column(String(255), nullable=False)
    link = Column(String(255), nullable=True)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(BigInteger, nullable=True)
    dedupe_key = Column(String(150), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} type={self.type!r}>"
