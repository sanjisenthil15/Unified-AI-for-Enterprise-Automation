"""
models/notification.py

SQLAlchemy ORM model for the `notifications` table.
A simple per-user activity feed (task assigned, chat message, sprint
created). Created directly by other modules' service functions — no
event bus, matching how lightly coupled this app's modules already are.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Notification(Base):
    """A single notification for one user."""

    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String(50), nullable=False)
    message = Column(String(255), nullable=False)
    link = Column(String(255), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} type={self.type!r}>"
