"""Guards for the PostgreSQL / Alembic baseline."""

from sqlalchemy import inspect, text

from config.database import engine

EXPECTED_TABLES = {
    "roles", "users", "employees", "job_postings", "resumes",
    "candidates", "support_tickets", "incidents", "alembic_version",
}
EXPECTED_ROLES = {"admin", "hr_manager", "support_agent", "recruiter", "employee", "viewer"}


def test_is_postgres():
    assert engine.dialect.name == "postgresql"


def test_all_baseline_tables_exist():
    names = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - names
    assert not missing, f"missing tables: {missing}"


def test_seeded_roles_present():
    with engine.connect() as c:
        names = {r[0] for r in c.execute(text("SELECT name FROM roles"))}
    assert EXPECTED_ROLES.issubset(names)


def test_alembic_at_head():
    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert rev, "alembic_version table is empty — run `alembic upgrade head`"


def test_updated_at_triggers_exist():
    with engine.connect() as c:
        trigs = {r[0] for r in c.execute(text(
            "SELECT trigger_name FROM information_schema.triggers"
        ))}
    assert "trg_users_updated_at" in trigs
    assert "trg_resumes_updated_at" in trigs
