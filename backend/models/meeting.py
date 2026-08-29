"""
models/meeting.py

SQLAlchemy ORM model for the `meetings` table.
Used by the Meeting Intelligence module.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Meeting(Base):
    """A recorded meeting submitted for AI transcription and summarisation."""

    __tablename__ = "meetings"

    id = Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)

    created_by = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title        = Column(String(255),  nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Integer,      nullable=True)
    audio_path   = Column(String(512),  nullable=True)

    status = Column(
        Enum("pending", "transcribing", "summarizing", "completed", "failed"),
        nullable=False,
        default="pending",
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} status={self.status!r}>"
