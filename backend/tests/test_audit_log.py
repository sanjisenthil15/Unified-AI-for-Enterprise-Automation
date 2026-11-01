"""Phase 4.5 — audit trail: transactional recording, actor + correlation
id, no secrets, append-only enforcement, Admin-only read API."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from config.database import SessionLocal, engine
from models.audit_log import AuditLog
from models.project import Project
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
AUDIT = "/api/v1/audit-logs"


def _email(tag):
    return f"pytest_{tag}_{uuid.uuid4().hex[:8]}@example.com"


def _rows(entity_type, entity_id):
    db = SessionLocal()
    try:
        return (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.id)
            .all()
        )
    finally:
        db.close()


def test_project_lifecycle_is_audited_with_actor_and_correlation_id(client, new_user):
    admin = new_user("Audit Admin")
    r = client.post(f"{EMP_BASE}/projects", headers={**admin["headers"], "X-Request-ID": "pytest-corr-1"},
                    json={"name": f"Project {_email('a')}"})
    assert r.status_code == 201, r.text
    assert r.headers["x-request-id"] == "pytest-corr-1"
    project_id = r.json()["id"]
    r = client.patch(f"{EMP_BASE}/projects/{project_id}/status", headers=admin["headers"], json={"status": "active"})
    assert r.status_code == 200, r.text
    generated_corr = r.headers["x-request-id"]

    rows = _rows("project", project_id)
    assert [row.action for row in rows] == ["project.created", "project.status_changed"]
    created, changed = rows
    assert created.actor_user_id == admin["id"] and created.actor_role == "admin"
    assert created.correlation_id == "pytest-corr-1"
    assert created.before is None and created.after["status"] == "planning"
    assert changed.before == {"status": "planning"} and changed.after == {"status": "active"}
    assert changed.correlation_id == generated_corr != "pytest-corr-1"


def test_unsafe_correlation_header_is_replaced(client, new_user):
    admin = new_user("Audit Admin")
    r = client.get("/api/v1/auth/me", headers={**admin["headers"], "X-Request-ID": "bad id; DROP TABLE"})
    assert r.headers["x-request-id"] != "bad id; DROP TABLE"
    assert len(r.headers["x-request-id"]) == 32


def test_rolled_back_change_leaves_no_audit_row(new_user):
    db = SessionLocal()
    name = f"Project {_email('rb')}"
    try:
        db.add(Project(name=name, status="planning"))
        db.flush()  # the listener writes the audit row here...
        project_id = db.query(Project.id).filter(Project.name == name).scalar()
        assert project_id is not None
        db.rollback()  # ...and this undoes both
    finally:
        db.close()
    assert _rows("project", project_id) == []


def test_password_events_never_store_secrets(client, new_user):
    admin = new_user("Audit Admin")
    email = _email("pw")
    roles = client.get("/api/v1/auth/roles", headers=admin["headers"]).json()
    r = client.post(f"{EMP_BASE}/employees", headers=admin["headers"], json={
        "full_name": "Audit Employee", "email": email,
        "role_id": next(x["id"] for x in roles if x["name"] == "employee"),
        "job_title": "Engineer", "hire_date": "2026-01-01",
    })
    temp_password = r.json()["temporary_password"]
    emp_headers = complete_first_login(client, email, temp_password)
    user_id = client.get("/api/v1/auth/me", headers=emp_headers).json()["id"]
    reset = client.post(f"/api/v1/auth/users/{user_id}/reset-password", headers=admin["headers"])
    assert reset.status_code == 200
    new_temp = reset.json()["temporary_password"]
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPass9"}).status_code == 401

    rows = _rows("user", user_id)
    actions = [row.action for row in rows]
    assert "user.created" in actions
    assert "auth.login_succeeded" in actions
    assert "user.password_changed" in actions
    assert "user.password_reset" in actions
    assert "auth.login_failed" in actions
    reset_row = next(row for row in rows if row.action == "user.password_reset")
    assert reset_row.actor_user_id == admin["id"]
    assert reset_row.after["must_change_password"] is True

    # Nothing secret anywhere in this user's trail.
    blob = " ".join(str(row.before) + str(row.after) for row in rows)
    for secret in (temp_password, new_temp, "WrongPass9", "FirstLogin1", "hashed_password", "token_version", "$2b$"):
        assert secret not in blob, secret


def test_audit_log_is_append_only_at_the_database_level(new_user):
    db = SessionLocal()
    try:
        from core import audit
        audit.record_event(db, "pytest.append_only_probe", "pytest", "1")
        db.commit()
        row_id = db.query(AuditLog.id).filter(AuditLog.action == "pytest.append_only_probe").order_by(AuditLog.id.desc()).first()[0]
    finally:
        db.close()

    for statement in (
        f"UPDATE audit_logs SET action = 'tampered' WHERE id = {row_id}",
        f"DELETE FROM audit_logs WHERE id = {row_id}",
        "TRUNCATE audit_logs",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            with engine.begin() as conn:
                conn.execute(text(statement))


def test_audit_api_is_admin_only_and_filters(client, new_user):
    admin = new_user("Audit Admin")
    for role in ("hr_manager", "manager", "employee", "viewer", "support_agent", "recruiter"):
        other = new_user(f"Audit {role}", role=role)
        assert client.get(AUDIT, headers=other["headers"]).status_code == 403, role

    r = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={"name": f"Project {_email('f')}"})
    project_id = r.json()["id"]

    page = client.get(AUDIT, headers=admin["headers"], params={"entity_type": "project", "entity_id": project_id})
    assert page.status_code == 200
    items = page.json()["items"]
    assert [i["action"] for i in items] == ["project.created"]
    assert items[0]["actor_name"] == "Audit Admin"

    by_prefix = client.get(AUDIT, headers=admin["headers"], params={"action": "project.", "limit": 1}).json()
    assert len(by_prefix["items"]) == 1 and by_prefix["items"][0]["action"].startswith("project.")
    assert by_prefix["next_before_id"] is not None
    older = client.get(AUDIT, headers=admin["headers"],
                       params={"action": "project.", "limit": 1, "before_id": by_prefix["next_before_id"]}).json()
    assert older["items"][0]["id"] < by_prefix["items"][0]["id"]

    # No write surface at all.
    assert client.post(AUDIT, headers=admin["headers"], json={}).status_code == 405
    assert client.delete(f"{AUDIT}/{items[0]['id']}", headers=admin["headers"]).status_code in (404, 405)
