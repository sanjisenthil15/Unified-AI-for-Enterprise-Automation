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

TEST_EMAIL_LIKE = "pytest\\_%@example.com"


def _cleanup_test_rows() -> None:
    """Remove any rows created by tests (identified by the pytest_*@example.com email)."""
    with engine.begin() as conn:
        user_ids = [
            r[0] for r in conn.execute(
                text("SELECT id FROM users WHERE email LIKE :p ESCAPE '\\'"),
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
        conn.execute(text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": user_ids})


@pytest.fixture(scope="session", autouse=True)
def _db_cleanup():
    _cleanup_test_rows()
    yield
    _cleanup_test_rows()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


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
        "role_id": 1,  # admin (seeded by the initial migration)
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
