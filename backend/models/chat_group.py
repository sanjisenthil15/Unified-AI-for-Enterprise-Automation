"""
models/chat_group.py

SQLAlchemy ORM model for the `chat_groups` table.
A Discord-style group, always scoped to one Project, created by that
project's team lead (or admin/hr_manager) and containing one or more
Channels (see models/chat_channel.py).
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, BigInteger, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class ChatGroup(Base):
    """A project-scoped chat group containing one or more channels."""

    __tablename__ = "chat_groups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="RESTRICT"),
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
    project = relationship("Project")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    members = relationship("ChatGroupMember", back_populates="group", cascade="all, delete-orphan")
    channels = relationship("ChatChannel", back_populates="group", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChatGroup id={self.id} name={self.name!r} project_id={self.project_id}>"
