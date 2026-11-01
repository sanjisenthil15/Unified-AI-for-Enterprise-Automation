"""account security: first-login password change + session versioning

Adds credential-lifecycle columns to users. Backward compatible: every
existing account gets must_change_password = false and token_version = 0,
so nobody is forced to change their password and existing sessions keep
working (tokens without a `ver` claim are treated as version 0).

Revision ID: f36f281e2838
Revises: b2c3d4e5f6a7
Create Date: 2026-11-01 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f36f281e2838"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false(),
        comment="True while the account still uses an HR-issued temporary password",
    ))
    op.add_column("users", sa.Column(
        "token_version", sa.Integer(), nullable=False, server_default="0",
        comment="Embedded in JWTs as `ver`; incrementing it revokes all earlier sessions",
    ))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column(
        "password_reset_by_id", sa.BigInteger(), nullable=True,
        comment="Who last issued an administrative password reset for this account",
    ))
    op.add_column("users", sa.Column("password_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_users_password_reset_by_id_users", "users", "users",
        ["password_reset_by_id"], ["id"], onupdate="CASCADE", ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_password_reset_by_id_users", "users", type_="foreignkey")
    op.drop_column("users", "password_reset_at")
    op.drop_column("users", "password_reset_by_id")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "token_version")
    op.drop_column("users", "must_change_password")
