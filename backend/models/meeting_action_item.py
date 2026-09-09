"""
models/meeting_action_item.py

SQLAlchemy ORM model for the `meeting_action_items` table.

An action item is extracted by the AI analysis step, but ASSIGNMENT IS
MANUAL in the MVP:

    - the AI fills `description`, `assignee_name_raw` (the raw name it heard),
      and `ai_confidence`; it does NOT resolve that to a person.
    - a human then sets `assigned_to_user_id` / `assigned_to_employee_id`
      via the API and `assignment_method` becomes "manual".

Future automatic assignment needs NO schema change: a resolver reads
`assignee_name_raw` + `ai_confidence`, writes `assigned_to_user_id`, and sets
`assignment_method` = "ai".
"""

from sqlalchemy import (
    Column, String, Text, Float, Date, DateTime, ForeignKey, Enum, BigInteger,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base

ACTION_ITEM_STATUSES        = ("pending", "in_progress", "completed", "cancelled")
ACTION_ITEM_PRIORITIES      = ("low", "medium", "high")
ACTION_ITEM_SOURCES         = ("ai", "manual")
ACTION_ITEM_ASSIGN_METHODS  = ("unassigned", "manual", "ai")


class MeetingActionItem(Base):
    """A task extracted from a meeting; assigned manually in the MVP."""

    __tablename__ = "meeting_action_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    meeting_id = Column(
        BigInteger,
        ForeignKey("meetings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_id = Column(
        BigInteger,
        ForeignKey("meeting_analyses.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    description = Column(Text, nullable=False)

    # --- assignment (manual in MVP) ----------------------------------- #
    assigned_to_user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_to_employee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_name_raw = Column(
        String(255), nullable=True,
        comment="Raw assignee mention from the AI — NOT resolved to a person",
    )
    assignment_method = Column(
        Enum(*ACTION_ITEM_ASSIGN_METHODS, name="meeting_action_item_assignment_method"),
        nullable=False,
        default="unassigned",
        server_default="unassigned",
    )

    # --- scheduling / tracking -------------------------------------- #
    due_date = Column(Date, nullable=True)
    priority = Column(
        Enum(*ACTION_ITEM_PRIORITIES, name="meeting_action_item_priority"),
        nullable=True,
    )
    status = Column(
        Enum(*ACTION_ITEM_STATUSES, name="meeting_action_item_status"),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )

    # --- provenance / future auto-assignment ----------------------- #
    source = Column(
        Enum(*ACTION_ITEM_SOURCES, name="meeting_action_item_source"),
        nullable=False,
        default="ai",
        server_default="ai",
    )
    ai_confidence = Column(Float, nullable=True, comment="0-1 confidence from the extractor")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- relationships -------------------------------------------- #
    meeting            = relationship("Meeting", back_populates="action_items")
    analysis           = relationship("MeetingAnalysis", back_populates="action_items")
    assigned_user      = relationship("User",     foreign_keys=[assigned_to_user_id])
    assigned_employee  = relationship("Employee", foreign_keys=[assigned_to_employee_id])

    def __repr__(self) -> str:
        return f"<MeetingActionItem id={self.id} meeting_id={self.meeting_id} status={self.status!r}>"
