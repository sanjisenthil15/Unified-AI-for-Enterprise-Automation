"""
models/incident.py

SQLAlchemy ORM model for the `incidents` table.
Used by the Incident Management module.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Incident(Base):
    """An operational incident reported by a user."""

    __tablename__ = "incidents"

    id = Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)

    reported_by = Column(
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

    title           = Column(String(255), nullable=False)
    description     = Column(Text,        nullable=False)
    affected_system = Column(String(120),  nullable=True)
    root_cause      = Column(Text,         nullable=True)

    severity = Column(
        Enum("low", "medium", "high", "critical"),
        nullable=False,
        default="medium",
        index=True,
    )
    status = Column(
        Enum("open", "investigating", "resolved", "closed"),
        nullable=False,
        default="open",
        index=True,
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
    reporter = relationship("User", foreign_keys=[reported_by])
    assignee = relationship("User", foreign_keys=[assigned_to])

    def __repr__(self) -> str:
        return f"<Incident id={self.id} severity={self.severity!r} status={self.status!r}>"
