"""
Shared pytest fixtures.

These are integration tests: they run the real FastAPI app against the
PostgreSQL database configured in backend/.env. Start the DB and apply
migrations first:

    docker compose up -d db      # or use a local PostgreSQL
    cd backend && alembic upgrade head
    pytest
"""

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from config.database import SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from sqlalchemy import text  # noqa: E402

TEST_EMAIL_LIKE = "%pytest%"


def _cleanup_test_rows() -> None:
    """Remove any rows created by tests (identified by the pytest_*@example.com email).

    Uses a plain substring LIKE (no ESCAPE clause) — an ESCAPE-based
    anchored pattern here previously matched zero rows under Postgres
    (confirmed by direct repro: a freshly inserted
    'pytest_probe@example.com' row did not match
    "pytest\\_%@example.com" ESCAPE '\\'), silently leaving every test
    run's rows in the database. "pytest" never appears in real data, so
    a simple substring match is both correct and actually works.
    """
    with engine.begin() as conn:
        # sprints.project_id is ON DELETE RESTRICT — must clear sprints (and their
        # cascading tasks/snapshots) before the projects they belong to.
        conn.execute(text(
            "DELETE FROM sprints WHERE project_id IN "
            "(SELECT id FROM projects WHERE name LIKE 'Project %pytest%')"
        ))
        # Test project names embed the test's unique_email, e.g. "Project pytest_xyz@example.com"
        conn.execute(text("DELETE FROM projects WHERE name LIKE 'Project %pytest%'"))

        user_ids = [
            r[0] for r in conn.execute(
                text("SELECT id FROM users WHERE email LIKE :p"),
                {"p": TEST_EMAIL_LIKE},
            )
        ]
        if not user_ids:
            return
        conn.execute(text(
            "DELETE FROM resumes WHERE job_posting_id IN "
            "(SELECT id FROM job_postings WHERE created_by = ANY(:ids))"
        ), {"ids": user_ids})
        conn.execute(text("DELETE FROM job_postings WHERE created_by = ANY(:ids)"), {"ids": user_ids})
        # meeting children cascade from meetings (ON DELETE CASCADE)
        conn.execute(text("DELETE FROM meetings WHERE created_by = ANY(:ids)"), {"ids": user_ids})
        # manager_chat_threads.{employee_id,manager_user_id} are ON DELETE RESTRICT
        # — messages cascade from the thread, but the thread itself must go first.
        conn.execute(text(
            "DELETE FROM manager_chat_threads WHERE manager_user_id = ANY(:ids) OR employee_id IN "
            "(SELECT id FROM employees WHERE user_id = ANY(:ids))"
        ), {"ids": user_ids})
        # attendance_records.employee_id and sprints.created_by are ON DELETE RESTRICT/SET NULL
        # respectively — clear attendance before the employee; any remaining test
        # sprints (created_by a test user, on a non-test-named project) too.
        conn.execute(text(
            "DELETE FROM attendance_records WHERE employee_id IN "
            "(SELECT id FROM employees WHERE user_id = ANY(:ids))"
        ), {"ids": user_ids})
        conn.execute(text(
            "DELETE FROM sprints WHERE created_by IN "
            "(SELECT id FROM employees WHERE user_id = ANY(:ids))"
        ), {"ids": user_ids})
        conn.execute(text("DELETE FROM notifications WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        # employees.user_id is ON DELETE RESTRICT — must clear it before the user
        conn.execute(text("DELETE FROM employees WHERE user_id = ANY(:ids)"), {"ids": user_ids})
        conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": user_ids})


@pytest.fixture(scope="session", autouse=True)
def _db_cleanup():
    _cleanup_test_rows()
    yield
    _cleanup_test_rows()


@pytest.fixture(scope="session", autouse=True)
def _meeting_storage_tmp(tmp_path_factory):
    """Point Meeting Intelligence file storage at a throwaway dir for the whole run."""
    from modules.meeting_intelligence import storage as _storage
    from modules.meeting_intelligence.config import meeting_settings

    original = meeting_settings.storage_dir
    meeting_settings.storage_dir = str(tmp_path_factory.mktemp("meeting_storage"))
    _storage._default_storage = None
    yield
    meeting_settings.storage_dir = original
    _storage._default_storage = None


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _promote_to_role(email: str, role_name: str) -> None:
    """Test-only helper: /auth/register always assigns 'employee' (anyone
    self-granting a privileged role would be a real security hole), so
    fixtures that need a privileged test user promote them directly via
    the DB afterward — same pattern as the meeting_owner fixture below."""
    from models.role import Role
    from models.user import User

    session = SessionLocal()
    try:
        role = session.query(Role).filter(Role.name == role_name).first()
        user = session.query(User).filter(User.email == email).first()
        user.role_id = role.id
        session.commit()
    finally:
        session.close()


@pytest.fixture
def new_user(client):
    """Factory: register + log in a fresh user (promoted to admin, matching
    this fixture's historical behavior), return {id, email, headers}."""
    def _make(full_name: str = "Pytest User", role: str = "admin") -> dict:
        email = f"pytest_{uuid.uuid4().hex[:10]}@example.com"
        password = "Str0ngPass1"
        r = client.post("/api/v1/auth/register", json={
            "full_name": full_name, "email": email, "password": password,
        })
        assert r.status_code == 201, r.text
        _promote_to_role(email, role)
        r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = client.get("/api/v1/auth/me", headers=headers).json()
        return {"id": me["id"], "email": email, "headers": headers}

    return _make


@pytest.fixture
def unique_email() -> str:
    return f"pytest_{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def db():
    """A raw SQLAlchemy session for ORM-level tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def meeting_owner(db) -> int:
    """A user id to own meetings. Removes its meetings + itself on teardown."""
    import uuid as _uuid
    from models.user import User
    from models.meeting import Meeting

    user = User(
        role_id=1,
        full_name="MI Owner",
        email=f"pytest_{_uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    db.commit()
    uid = user.id
    yield uid
    db.query(Meeting).filter(Meeting.created_by == uid).delete()
    db.commit()
    db.query(User).filter(User.id == uid).delete()
    db.commit()


@pytest.fixture
def admin_headers(client, unique_email) -> dict:
    """Register + log in a fresh admin user, return an Authorization header."""
    password = "Str0ngPass1"
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Pytest Admin",
        "email": unique_email,
        "password": password,
    })
    assert r.status_code == 201, r.text
    _promote_to_role(unique_email, "admin")
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
