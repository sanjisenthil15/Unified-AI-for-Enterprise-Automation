"""
models/manager_chat_message.py

SQLAlchemy ORM model for the `manager_chat_messages` table.
See models/manager_chat_thread.py for why these are named `Manager*`.
"""

from sqlalchemy import Column, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class ManagerChatMessage(Base):
    """One message within a manager<->employee chat thread."""

    __tablename__ = "manager_chat_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    thread_id = Column(
        BigInteger,
        ForeignKey("manager_chat_threads.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    body = Column(Text, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    thread = relationship("ManagerChatThread", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_user_id])

    def __repr__(self) -> str:
        return f"<ManagerChatMessage id={self.id} thread_id={self.thread_id}>"
