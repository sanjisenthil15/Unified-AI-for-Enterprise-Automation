"""
models/ticket.py

SQLAlchemy ORM model for the `support_tickets` table.
Used by the Customer Support AI module.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.mysql import BIGINT, SMALLINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class SupportTicket(Base):
    """Customer support ticket submitted by a user."""

    __tablename__ = "support_tickets"

    id = Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)

    submitted_by = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_to = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    subject     = Column(String(255), nullable=False)
    description = Column(Text,        nullable=False)

    priority = Column(
        Enum("low", "medium", "high", "critical"),
        nullable=False,
        default="medium",
        index=True,
    )
    status = Column(
        Enum("open", "in_progress", "resolved", "closed", "escalated"),
        nullable=False,
        default="open",
        index=True,
    )
    channel = Column(
        Enum("web", "email", "chat", "api"),
        nullable=False,
        default="web",
    )

    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    submitter = relationship("User", foreign_keys=[submitted_by])
    agent     = relationship("User", foreign_keys=[assigned_to])

    def __repr__(self) -> str:
        return f"<SupportTicket id={self.id} status={self.status!r}>"
