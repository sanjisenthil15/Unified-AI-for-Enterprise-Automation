"""
models/chat_channel_message.py

SQLAlchemy ORM model for the `chat_channel_messages` table. Kept separate
from ManagerChatMessage (1:1 DMs) rather than merged — a channel has N
members, so a single read_at column (only meaningful for a 2-party DM)
doesn't generalize; read state for groups lives on ChatGroupMember instead.
"""

from sqlalchemy import Column, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class ChatChannelMessage(Base):
    """One message within a chat group's channel."""

    __tablename__ = "chat_channel_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    channel_id = Column(
        BigInteger,
        ForeignKey("chat_channels.id", onupdate="CASCADE", ondelete="CASCADE"),
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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    channel = relationship("ChatChannel", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_user_id])

    def __repr__(self) -> str:
        return f"<ChatChannelMessage id={self.id} channel_id={self.channel_id}>"
