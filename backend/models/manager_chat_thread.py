"""
models/manager_chat_thread.py

SQLAlchemy ORM model for the `manager_chat_threads` table.
A 1:1 conversation between an Employee and their manager (a User who is
either that employee's project team lead, or admin/hr_manager).

Named `Manager*` (not `Chat*`) because `ChatMessage`/`chat_messages`
already exist in models/ticket.py for the Customer Support module.
"""

from sqlalchemy import Column, DateTime, ForeignKey, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class ManagerChatThread(Base):
    """A 1:1 chat thread between an employee and their manager."""

    __tablename__ = "manager_chat_threads"
    __table_args__ = (
        UniqueConstraint("employee_id", "manager_user_id", name="uq_manager_chat_thread_pair"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    employee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    manager_user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    employee = relationship("Employee", foreign_keys=[employee_id])
    manager_user = relationship("User", foreign_keys=[manager_user_id])
    messages = relationship(
        "ManagerChatMessage", back_populates="thread",
        cascade="all, delete-orphan", order_by="ManagerChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ManagerChatThread employee_id={self.employee_id} manager_user_id={self.manager_user_id}>"
