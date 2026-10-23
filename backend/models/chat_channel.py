"""
models/chat_channel.py

SQLAlchemy ORM model for the `chat_channels` table.
A topic channel within a ChatGroup (e.g. "general", "leave", "frontend").
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class ChatChannel(Base):
    """A channel within a chat group."""

    __tablename__ = "chat_channels"
    __table_args__ = (
        UniqueConstraint("group_id", "name", name="uq_chat_channel_name_per_group"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    group_id = Column(
        BigInteger,
        ForeignKey("chat_groups.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)

    created_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    group = relationship("ChatGroup", back_populates="channels")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    messages = relationship(
        "ChatChannelMessage", back_populates="channel",
        cascade="all, delete-orphan", order_by="ChatChannelMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<ChatChannel id={self.id} name={self.name!r} group_id={self.group_id}>"
