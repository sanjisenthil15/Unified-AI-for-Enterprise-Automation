"""
models/meeting_participant.py

SQLAlchemy ORM model for the `meeting_participants` table.

Participants are added MANUALLY (MVP). A participant may be linked to a real
User and/or Employee record, but `display_name` is always present so external
/ unregistered attendees can be recorded too.

Participants are distinct from `meeting_speakers` — a speaker is a
diarization-detected voice ("Speaker 1"), which may later be mapped to a
participant/employee.
"""

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Enum, BigInteger, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base

MEETING_PARTICIPANT_ROLES = ("organizer", "attendee", "guest")


class MeetingParticipant(Base):
    """A person recorded as having attended a meeting."""

    __tablename__ = "meeting_participants"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_participant_user"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    meeting_id = Column(
        BigInteger,
        ForeignKey("meetings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional links into the existing people structure.
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    display_name = Column(String(255), nullable=False)
    role = Column(
        Enum(*MEETING_PARTICIPANT_ROLES, name="meeting_participant_role"),
        nullable=False,
        default="attendee",
        server_default="attendee",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # --- relationships -------------------------------------------------- #
    meeting  = relationship("Meeting", back_populates="participants")
    user     = relationship("User",     foreign_keys=[user_id])
    employee = relationship("Employee", foreign_keys=[employee_id])

    def __repr__(self) -> str:
        return f"<MeetingParticipant id={self.id} meeting_id={self.meeting_id} name={self.display_name!r}>"
