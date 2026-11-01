"""
models/meeting_action_item.py

SQLAlchemy ORM model for the `meeting_action_items` table.

An action item is extracted by the AI analysis step, with a formal review
lifecycle: proposed -> confirmed -> converted (or proposed -> rejected).
"""

from sqlalchemy import (
    Column, String, Text, Float, Date, DateTime, ForeignKey, Enum, BigInteger, Boolean, Index, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base

ACTION_ITEM_STATUSES        = ("pending", "in_progress", "completed", "cancelled")
ACTION_ITEM_PRIORITIES      = ("low", "medium", "high")
ACTION_ITEM_SOURCES         = ("ai", "manual")
ACTION_ITEM_ASSIGN_METHODS  = ("unassigned", "manual", "ai")
ACTION_ITEM_REVIEW_STATUSES = ("proposed", "confirmed", "rejected", "converted")


class MeetingActionItem(Base):
    """A task extracted from a meeting; governed by an approval review lifecycle."""

    __tablename__ = "meeting_action_items"
    # Mirrors the indexes created by migration c1d2e3f4a5b6 so autogenerate
    # never proposes dropping them — the partial unique index is what stops
    # one sprint task being linked to two action items (duplicate conversion).
    __table_args__ = (
        Index("ix_meeting_action_items_review", "meeting_id", "review_status"),
        Index(
            "uq_meeting_action_items_converted_task", "converted_sprint_task_id",
            unique=True, postgresql_where=text("converted_sprint_task_id IS NOT NULL"),
        ),
    )

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

    # --- review governance (Submodule 4.2) -------------------------- #
    review_status = Column(
        String(32),
        nullable=False,
        default="proposed",
        server_default="proposed",
    )
    reviewed_by_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    final_description = Column(Text, nullable=True)
    is_legacy_conversion = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # --- provenance / future auto-assignment ----------------------- #
    source = Column(
        Enum(*ACTION_ITEM_SOURCES, name="meeting_action_item_source"),
        nullable=False,
        default="ai",
        server_default="ai",
    )
    ai_confidence = Column(Float, nullable=True, comment="0-1 confidence from the extractor")

    # Set once this action item has been turned into a Sprint task.
    # RESTRICT prevents orphaned converted states if task is deleted.
    converted_sprint_task_id = Column(
        BigInteger,
        ForeignKey("sprint_tasks.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )

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
    reviewed_by        = relationship("User",     foreign_keys=[reviewed_by_id])

    @property
    def reviewed_by_name(self) -> str | None:
        return self.reviewed_by.full_name if self.reviewed_by else None

    def __repr__(self) -> str:
        return f"<MeetingActionItem id={self.id} meeting_id={self.meeting_id} status={self.status!r} review_status={self.review_status!r}>"
