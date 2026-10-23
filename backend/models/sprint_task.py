"""
models/sprint_task.py

SQLAlchemy ORM model for the `sprint_tasks` table.
A unit of work within a Sprint, assigned to one Employee.
"""

from sqlalchemy import Column, String, Text, Date, DateTime, ForeignKey, Enum, BigInteger, Integer, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class SprintTask(Base):
    """A task within a sprint, assigned to one employee."""

    __tablename__ = "sprint_tasks"
    __table_args__ = (
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_sprint_task_progress_range"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    sprint_id = Column(
        BigInteger,
        ForeignKey("sprints.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(
        Enum("todo", "in_progress", "blocked", "done", name="sprint_task_status"),
        nullable=False,
        default="todo",
        index=True,
    )
    progress_percent = Column(Integer, nullable=False, default=0)
    due_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    sprint = relationship("Sprint", back_populates="tasks")
    assignee = relationship("Employee", foreign_keys=[assignee_id])

    def __repr__(self) -> str:
        return f"<SprintTask id={self.id} title={self.title!r} status={self.status!r}>"
