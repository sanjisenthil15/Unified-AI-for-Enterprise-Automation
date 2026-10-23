"""
models/sprint_task_snapshot.py

SQLAlchemy ORM model for the `sprint_task_snapshots` table.
A daily snapshot of remaining/total task counts for a sprint, used to
render a burndown chart. Captured lazily (on view, not via a cron) since
this app has no background scheduler.
"""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class SprintTaskSnapshot(Base):
    """One day's remaining/total task counts for a sprint's burndown chart."""

    __tablename__ = "sprint_task_snapshots"
    __table_args__ = (
        UniqueConstraint("sprint_id", "snapshot_date", name="uq_sprint_snapshot_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    sprint_id = Column(
        BigInteger,
        ForeignKey("sprints.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date = Column(Date, nullable=False)
    remaining_count = Column(Integer, nullable=False)
    total_count = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    sprint = relationship("Sprint")

    def __repr__(self) -> str:
        return f"<SprintTaskSnapshot sprint_id={self.sprint_id} date={self.snapshot_date} remaining={self.remaining_count}>"
