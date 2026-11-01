"""add manager role

Adds a 'manager' role for project-scoped management.
Idempotent — ON CONFLICT DO NOTHING.

Revision ID: a1b2c3d4e5f6
Revises: 4f6d3fc0cb83
Create Date: 2026-10-31 17:30:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "4f6d3fc0cb83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (name, description)
        VALUES ('manager', 'Project-scoped management: sprints, team oversight, action items')
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    # Only delete if no users are assigned to this role
    op.execute(
        """
        DELETE FROM roles
        WHERE name = 'manager'
          AND NOT EXISTS (SELECT 1 FROM users WHERE users.role_id = roles.id)
        """
    )
