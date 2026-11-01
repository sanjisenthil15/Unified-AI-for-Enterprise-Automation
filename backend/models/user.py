"""
models/user.py

SQLAlchemy ORM model for the `users` table.
Stores login credentials and links each user to an RBAC role.
Passwords are NEVER stored in plain text — only bcrypt hashes.
"""

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, BigInteger, Integer
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class User(Base):
    """
    Core user entity.  Every person who can log in has exactly one
    User record linked to one Role.

    Soft-delete via `deleted_at`: set to a timestamp to deactivate
    without losing audit history or breaking foreign keys.
    """

    __tablename__ = "users"

    # ------------------------------------------------------------------ #
    # Primary key
    # ------------------------------------------------------------------ #
    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # ------------------------------------------------------------------ #
    # Foreign key — Role (RBAC)
    # ------------------------------------------------------------------ #
    role_id = Column(
        Integer,
        ForeignKey("roles.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="FK → roles.id — determines what this user can access",
    )

    # ------------------------------------------------------------------ #
    # Identity fields
    # ------------------------------------------------------------------ #
    full_name = Column(
        String(120),
        nullable=False,
        comment="Display name shown throughout the application",
    )
    email = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Primary login identifier — must be unique across all users",
    )
    hashed_password = Column(
        String(255),
        nullable=False,
        comment="bcrypt hash of the user's password — never store plain text",
    )

    # ------------------------------------------------------------------ #
    # Account state
    # ------------------------------------------------------------------ #
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="False = account disabled but not deleted",
    )

    # ------------------------------------------------------------------ #
    # Credential lifecycle
    # ------------------------------------------------------------------ #
    must_change_password = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True while the account still uses an HR-issued temporary password",
    )
    token_version = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Embedded in JWTs as `ver`; incrementing it revokes all earlier sessions",
    )
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    password_reset_by_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        comment="Who last issued an administrative password reset for this account",
    )
    password_reset_at = Column(DateTime(timezone=True), nullable=True)

    # ------------------------------------------------------------------ #
    # Timestamps
    # ------------------------------------------------------------------ #
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Soft-delete timestamp — NULL means the account is active",
    )

    # ------------------------------------------------------------------ #
    # Relationships
    # ------------------------------------------------------------------ #
    role = relationship("Role", back_populates="users")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role_id={self.role_id}>"
