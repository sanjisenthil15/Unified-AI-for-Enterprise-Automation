"""seed demo admin user

Creates demo@demo.com / Demo1234 (role: admin) so the app can be run without
registering an account — used with AUTH_DISABLED=true, or just as a ready
login. Idempotent.

Revision ID: 296e1fa18ddc
Revises: f0861446d2df
Create Date: 2026-09-10 01:59:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "296e1fa18ddc"
down_revision: Union[str, Sequence[str], None] = "f0861446d2df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# bcrypt hash of "Demo1234"
_DEMO_HASH = "$2b$12$NpfVUPCrogJV4eoYhXI3q.wTE73haSBtO50Wd7OJuetUBij8wq38i"


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO users (role_id, full_name, email, hashed_password, is_active)
        SELECT r.id, 'Demo Admin', 'demo@demo.com', '{hash}', TRUE
        FROM roles r
        WHERE r.name = 'admin'
        ON CONFLICT (email) DO NOTHING
        """.format(hash=_DEMO_HASH)
    )


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE email = 'demo@demo.com'")
