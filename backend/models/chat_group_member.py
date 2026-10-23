"""
models/chat_group_member.py

SQLAlchemy ORM model for the `chat_group_members` table.
"""

from sqlalchemy import Column, DateTime, ForeignKey, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class ChatGroupMember(Base):
    """A user's membership in a ChatGroup. One read-marker per group (not
    per channel) — a deliberately simple MVP read-tracking choice."""

    __tablename__ = "chat_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_chat_group_member_pair"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    group_id = Column(
        BigInteger,
        ForeignKey("chat_groups.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    group = relationship("ChatGroup", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<ChatGroupMember group_id={self.group_id} user_id={self.user_id}>"
