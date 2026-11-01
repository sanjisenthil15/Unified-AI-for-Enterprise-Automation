"""submodule 4.2: meeting action-item approval & multi-manager architecture

Revision ID: c1d2e3f4a5b6
Revises: f36f281e2838
Create Date: 2026-11-01 11:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "f36f281e2838"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the single-active-Manager partial unique index
    op.execute("DROP INDEX IF EXISTS uq_single_active_manager")

    # 2. Add manager_user_id to projects (nullable, FK to users.id with RESTRICT on delete)
    op.add_column("projects", sa.Column(
        "manager_user_id", sa.BigInteger(), nullable=True,
        comment="The designated Manager assigned to this project"
    ))
    op.create_foreign_key(
        "fk_projects_manager_user_id",
        "projects", "users",
        ["manager_user_id"], ["id"],
        onupdate="CASCADE", ondelete="RESTRICT"
    )
    op.create_index("ix_projects_manager_user_id", "projects", ["manager_user_id"])

    # 3. Add review lifecycle columns to meeting_action_items
    op.add_column("meeting_action_items", sa.Column(
        "review_status", sa.String(32), nullable=False, server_default="proposed",
        comment="Review governance status: proposed, confirmed, rejected, converted"
    ))
    op.add_column("meeting_action_items", sa.Column(
        "reviewed_by_id", sa.BigInteger(), nullable=True,
        comment="User who confirmed or rejected this action item"
    ))
    op.add_column("meeting_action_items", sa.Column(
        "reviewed_at", sa.DateTime(timezone=True), nullable=True,
        comment="Timestamp when review decision was recorded"
    ))
    op.add_column("meeting_action_items", sa.Column(
        "rejection_reason", sa.Text(), nullable=True,
        comment="Required justification when review_status is rejected"
    ))
    op.add_column("meeting_action_items", sa.Column(
        "final_description", sa.Text(), nullable=True,
        comment="Human-edited approved task description; original raw AI text stays in description"
    ))
    op.add_column("meeting_action_items", sa.Column(
        "is_legacy_conversion", sa.Boolean(), nullable=False, server_default=sa.false(),
        comment="True exclusively for historical conversions predating Submodule 4.2"
    ))

    # Foreign key for reviewed_by_id (RESTRICT on delete to preserve audit trail)
    op.create_foreign_key(
        "fk_meeting_action_items_reviewer",
        "meeting_action_items", "users",
        ["reviewed_by_id"], ["id"],
        onupdate="CASCADE", ondelete="RESTRICT"
    )

    # 4. Data-driven backfills
    # 4a. Backfill missing assignee from linked sprint task if verifiable
    op.execute("""
        UPDATE meeting_action_items mai
        SET assigned_to_employee_id = st.assignee_id
        FROM sprint_tasks st
        WHERE mai.converted_sprint_task_id = st.id
          AND mai.assigned_to_employee_id IS NULL
          AND st.assignee_id IS NOT NULL
    """)

    # 4b. Backfill missing due_date from sprint task, fallback to sprint end_date. No fabricated dates!
    op.execute("""
        UPDATE meeting_action_items mai
        SET due_date = COALESCE(mai.due_date, st.due_date, s.end_date)
        FROM sprint_tasks st
        JOIN sprints s ON st.sprint_id = s.id
        WHERE mai.converted_sprint_task_id = st.id
          AND mai.due_date IS NULL
    """)

    # 4c. Backfill historical converted items: mark legacy conversion
    op.execute("""
        UPDATE meeting_action_items
        SET review_status = 'converted',
            final_description = description,
            is_legacy_conversion = TRUE
        WHERE converted_sprint_task_id IS NOT NULL
    """)

    # 4d. Backfill unconverted items to proposed
    op.execute("""
        UPDATE meeting_action_items
        SET review_status = 'proposed',
            is_legacy_conversion = FALSE
        WHERE converted_sprint_task_id IS NULL
    """)

    # 4e. Data-driven project manager assignment
    op.execute("""
        DO $$
        DECLARE
            v_manager_count INT;
            v_active_manager_id BIGINT;
            v_unassigned_project_count INT;
        BEGIN
            SELECT COUNT(*), MIN(u.id)
            INTO v_manager_count, v_active_manager_id
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE r.name = 'manager' AND u.is_active = TRUE AND u.deleted_at IS NULL;

            SELECT COUNT(*) INTO v_unassigned_project_count
            FROM projects WHERE manager_user_id IS NULL;

            IF v_manager_count = 1 THEN
                UPDATE projects SET manager_user_id = v_active_manager_id WHERE manager_user_id IS NULL;
                RAISE NOTICE 'Data-driven backfill: Assigned active Manager (user_id=%) to % unassigned projects.', 
                    v_active_manager_id, v_unassigned_project_count;
            ELSIF v_manager_count = 0 THEN
                RAISE NOTICE 'Data-driven backfill: No active Manager found. % projects remain unassigned.', 
                    v_unassigned_project_count;
            ELSE
                RAISE NOTICE 'Data-driven backfill: Multiple active Managers (%) detected. % projects left unassigned for manual Admin/HR assignment.', 
                    v_manager_count, v_unassigned_project_count;
            END IF;
        END $$;
    """)

    # 5. Database CHECK constraints
    # Constraint 1: Review status allowed values
    op.execute("""
        ALTER TABLE meeting_action_items
        ADD CONSTRAINT ck_action_items_review_status
        CHECK (review_status IN ('proposed', 'confirmed', 'rejected', 'converted'))
    """)

    # Constraint 2: Mandatory Assignee & Deadline for confirmed & new converted items
    op.execute("""
        ALTER TABLE meeting_action_items
        ADD CONSTRAINT ck_action_items_assignee_deadline
        CHECK (
            (review_status = 'confirmed' AND assigned_to_employee_id IS NOT NULL AND due_date IS NOT NULL)
            OR
            (review_status = 'converted' AND is_legacy_conversion = FALSE AND assigned_to_employee_id IS NOT NULL AND due_date IS NOT NULL)
            OR
            (review_status = 'converted' AND is_legacy_conversion = TRUE)
            OR
            (review_status IN ('proposed', 'rejected'))
        )
    """)

    # Constraint 3: Rejection consistency
    op.execute("""
        ALTER TABLE meeting_action_items
        ADD CONSTRAINT ck_action_items_rejection_reason
        CHECK (
            (review_status = 'rejected' AND rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)
            OR
            (review_status != 'rejected' AND rejection_reason IS NULL)
        )
    """)

    # Constraint 4: Conversion & Task link consistency
    op.execute("""
        ALTER TABLE meeting_action_items
        ADD CONSTRAINT ck_action_items_task_link
        CHECK (
            (review_status = 'converted' AND converted_sprint_task_id IS NOT NULL)
            OR
            (review_status IN ('proposed', 'confirmed', 'rejected') AND converted_sprint_task_id IS NULL)
        )
    """)

    # Constraint 5: Legacy consistency (legacy conversions must be converted with null attribution)
    op.execute("""
        ALTER TABLE meeting_action_items
        ADD CONSTRAINT ck_action_items_legacy_consistency
        CHECK (
            (is_legacy_conversion = TRUE AND review_status = 'converted' AND reviewed_by_id IS NULL AND reviewed_at IS NULL)
            OR
            (is_legacy_conversion = FALSE)
        )
    """)

    # Constraint 6: Reviewer attribution consistency
    op.execute("""
        ALTER TABLE meeting_action_items
        ADD CONSTRAINT ck_action_items_reviewer_attribution
        CHECK (
            (review_status = 'proposed' AND reviewed_by_id IS NULL AND reviewed_at IS NULL)
            OR
            (review_status IN ('confirmed', 'rejected') AND reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL)
            OR
            (review_status = 'converted' AND is_legacy_conversion = TRUE)
            OR
            (review_status = 'converted' AND is_legacy_conversion = FALSE AND reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL)
        )
    """)

    # 6. Foreign key on converted_sprint_task_id updated to RESTRICT
    op.execute("""
        ALTER TABLE meeting_action_items
        DROP CONSTRAINT IF EXISTS meeting_action_items_converted_sprint_task_id_fkey,
        ADD CONSTRAINT fk_meeting_action_items_converted_task
            FOREIGN KEY (converted_sprint_task_id)
            REFERENCES sprint_tasks(id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT
    """)

    # 7. Indices
    op.create_index(
        "uq_meeting_action_items_converted_task",
        "meeting_action_items",
        ["converted_sprint_task_id"],
        unique=True,
        postgresql_where=sa.text("converted_sprint_task_id IS NOT NULL")
    )
    op.create_index(
        "ix_meeting_action_items_review",
        "meeting_action_items",
        ["meeting_id", "review_status"]
    )

    # 8. Database-enforced triggers protecting is_legacy_conversion
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_prevent_legacy_insert()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.is_legacy_conversion = TRUE THEN
                RAISE EXCEPTION 'Security violation: New action items cannot be created with is_legacy_conversion = TRUE.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_action_items_protect_legacy_insert ON meeting_action_items;
        CREATE TRIGGER trg_action_items_protect_legacy_insert
        BEFORE INSERT ON meeting_action_items
        FOR EACH ROW
        EXECUTE FUNCTION trg_prevent_legacy_insert();

        CREATE OR REPLACE FUNCTION trg_prevent_legacy_escalation()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.is_legacy_conversion = FALSE AND NEW.is_legacy_conversion = TRUE THEN
                RAISE EXCEPTION 'Security violation: is_legacy_conversion cannot be set to TRUE on existing records.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_action_items_protect_legacy_update ON meeting_action_items;
        CREATE TRIGGER trg_action_items_protect_legacy_update
        BEFORE UPDATE ON meeting_action_items
        FOR EACH ROW
        EXECUTE FUNCTION trg_prevent_legacy_escalation();
    """)


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Preflight check: prevent destructive downgrade if multiple active managers exist
    active_managers = conn.execute(sa.text("""
        SELECT COUNT(*)
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE r.name = 'manager' AND u.is_active = true AND u.deleted_at IS NULL
    """)).scalar()

    if active_managers > 1:
        raise RuntimeError(
            f"ABORTING DOWNGRADE: Cannot restore single-manager restriction because {active_managers} "
            "active Managers exist. Safe rollback preparation required: An administrator must deactivate "
            "or reassign surplus Managers until at most 1 active Manager remains before running downgrade."
        )

    # 2. Drop triggers and functions
    op.execute("DROP TRIGGER IF EXISTS trg_action_items_protect_legacy_insert ON meeting_action_items")
    op.execute("DROP TRIGGER IF EXISTS trg_action_items_protect_legacy_update ON meeting_action_items")
    op.execute("DROP FUNCTION IF EXISTS trg_prevent_legacy_insert()")
    op.execute("DROP FUNCTION IF EXISTS trg_prevent_legacy_escalation()")

    # 3. Drop constraints & indices
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS ck_action_items_review_status")
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS ck_action_items_assignee_deadline")
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS ck_action_items_rejection_reason")
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS ck_action_items_task_link")
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS ck_action_items_legacy_consistency")
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS ck_action_items_reviewer_attribution")
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS fk_meeting_action_items_reviewer")

    op.drop_index("uq_meeting_action_items_converted_task", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_review", table_name="meeting_action_items")
    op.drop_index("ix_projects_manager_user_id", table_name="projects")

    # 4. Restore original foreign key (ON DELETE SET NULL)
    op.execute("ALTER TABLE meeting_action_items DROP CONSTRAINT IF EXISTS fk_meeting_action_items_converted_task")
    op.create_foreign_key(
        None, "meeting_action_items", "sprint_tasks",
        ["converted_sprint_task_id"], ["id"],
        onupdate="CASCADE", ondelete="SET NULL"
    )

    # 5. Drop columns
    op.drop_constraint("fk_projects_manager_user_id", "projects", type_="foreignkey")
    op.drop_column("projects", "manager_user_id")

    op.drop_column("meeting_action_items", "is_legacy_conversion")
    op.drop_column("meeting_action_items", "final_description")
    op.drop_column("meeting_action_items", "rejection_reason")
    op.drop_column("meeting_action_items", "reviewed_at")
    op.drop_column("meeting_action_items", "reviewed_by_id")
    op.drop_column("meeting_action_items", "review_status")

    # 6. Re-create single active manager unique index
    res = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'manager'")).fetchone()
    if res:
        manager_role_id = res[0]
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_single_active_manager
            ON users (role_id)
            WHERE role_id = {manager_role_id} AND deleted_at IS NULL AND is_active = true
        """)

