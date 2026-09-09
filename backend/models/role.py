"""
models/role.py

SQLAlchemy ORM model for the `roles` table.
Roles are seeded once (see the initial Alembic migration) and referenced
by every user record.

Seeded roles: admin, hr_manager, support_agent, recruiter, employee, viewer
"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Role(Base):
    """
    Represents a single access role in the RBAC system.
    Each role grants a specific set of permissions enforced in
    the dependency layer (core/dependencies.py).
    """

    __tablename__ = "roles"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique role identifier, e.g. 'admin', 'hr_manager', 'employee'",
    )
    description = Column(
        Text,
        nullable=True,
        comment="Human-readable explanation of what this role can do",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    # Back-reference from User model (populated lazily)
    users = relationship("User", back_populates="role", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"
