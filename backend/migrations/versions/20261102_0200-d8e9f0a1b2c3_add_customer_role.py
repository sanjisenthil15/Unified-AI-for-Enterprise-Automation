"""add customer role

Adds a 'customer' role for external customer support access.
Idempotent — ON CONFLICT DO NOTHING.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-02 02:00:00
"""
from typing import Sequence, Union
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (name, description)
        VALUES ('customer', 'External customer account for support ticket submission and tracking')
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM roles
        WHERE name = 'customer'
          AND NOT EXISTS (SELECT 1 FROM users WHERE users.role_id = roles.id)
        """
    )

