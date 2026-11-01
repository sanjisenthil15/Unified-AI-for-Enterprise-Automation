"""Phase 5.2 / 5.5 — API-level RBAC matrix and security regressions.

Every check here goes through the real HTTP API with a real JWT for each
role: hiding a button in the UI is never what's being tested."""
import io
import os
import uuid
from pathlib import Path

import pytest

ROLES = ("admin", "hr_manager", "support_agent", "recruiter", "employee", "viewer", "manager")


@pytest.fixture(scope="module")
def as_role(client):
    """One fresh account per role for the whole module: {role: headers}."""
    from tests.conftest import _promote_to_role

    accounts = {}
    for role in ROLES:
        email = f"pytest_p5_{role}_{uuid.uuid4().hex[:8]}@example.com"
        password = "Str0ngPass1"
        assert client.post("/api/v1/auth/register", json={
            "full_name": f"P5 {role}", "email": email, "password": password,
        }).status_code == 201
        _promote_to_role(email, role)
        token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        accounts[role] = {"headers": headers, "id": client.get("/api/v1/auth/me", headers=headers).json()["id"]}
    return accounts


# (method, path, json body, roles that must get past authorization)
MATRIX = [
    ("GET", "/api/v1/audit-logs", None, {"admin"}),
    ("POST", "/api/v1/escalations/run", None, {"admin"}),
    ("GET", "/api/v1/escalations", None, {"admin", "hr_manager"}),
    ("GET", "/api/v1/leave/requests", None, {"admin", "hr_manager"}),
    ("GET", "/api/v1/employee-management/employees", None, {"admin", "hr_manager", "manager"}),
    ("POST", "/api/v1/employee-management/employees", {}, {"admin", "hr_manager"}),
    ("POST", "/api/v1/employee-management/departments", {}, {"admin", "hr_manager"}),
    ("POST", "/api/v1/employee-management/projects", {}, {"admin", "hr_manager"}),
    # Viewer: read-only aggregate analytics; never workforce (named employees' workloads).
    ("GET", "/api/v1/analytics/overview", None, {"admin", "manager", "viewer"}),
    ("GET", "/api/v1/analytics/projects", None, {"admin", "manager", "viewer"}),
    ("GET", "/api/v1/analytics/operations", None, {"admin", "manager", "viewer"}),
    ("GET", "/api/v1/analytics/trends", None, {"admin", "manager", "viewer"}),
    ("GET", "/api/v1/analytics/workforce", None, {"admin", "manager"}),
    ("POST", "/api/v1/intelligence/refresh?scope=org", None, {"admin", "manager"}),
    ("GET", "/api/v1/recruitment/stats", None, {"admin", "hr_manager", "recruiter"}),
    ("POST", "/api/v1/recruitment/jobs", {}, {"admin", "hr_manager", "recruiter"}),
    ("POST", "/api/v1/customer-support/knowledge", {}, {"admin", "support_agent"}),
    ("POST", "/api/v1/customer-support/categories", {}, {"admin", "support_agent"}),
    ("PUT", "/api/v1/incidents/999999999", {}, {"admin", "support_agent", "manager"}),
    ("POST", "/api/v1/incidents", {}, {"admin", "hr_manager", "support_agent", "recruiter", "employee", "manager"}),
]


@pytest.mark.parametrize("method,path,body,allowed", MATRIX, ids=[f"{m} {p}" for m, p, _, _ in MATRIX])
def test_rbac_matrix(client, as_role, method, path, body, allowed):
    for role in ROLES:
        r = client.request(method, path, headers=as_role[role]["headers"], json=body)
        if role in allowed:
            assert r.status_code not in (401, 403), f"{role} wrongly refused {method} {path}: {r.status_code} {r.text}"
        else:
            assert r.status_code == 403, f"{role} not refused {method} {path}: {r.status_code} {r.text[:200]}"


def test_unauthenticated_and_tampered_tokens_are_refused(client, as_role):
    assert client.get("/api/v1/notifications/me").status_code == 401
    assert client.get("/api/v1/notifications/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    token = as_role["employee"]["headers"]["Authorization"].split()[1]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert client.get("/api/v1/notifications/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_hr_gets_no_org_wide_intelligence(client, as_role):
    """HR is an override role for HR work, not for executive analytics /
    AI intelligence (Admin & Manager only, as the endpoints document)."""
    hr = as_role["hr_manager"]["headers"]
    assert client.get("/api/v1/intelligence/project-risks", headers=hr).status_code == 403
    assert client.get("/api/v1/intelligence/sprint-delays", headers=hr).status_code == 403
    assert client.get("/api/v1/intelligence/workload-bottlenecks", headers=hr).status_code == 403
    assert client.post("/api/v1/intelligence/refresh", headers=hr, params={"scope": "org"}).status_code == 403


def test_viewer_cannot_write_anywhere_checked(client, as_role):
    viewer = as_role["viewer"]["headers"]
    for method, path, body in (
        ("POST", "/api/v1/incidents", {}),
        ("POST", "/api/v1/employee-management/projects", {}),
        ("POST", "/api/v1/recruitment/jobs", {}),
        ("POST", "/api/v1/customer-support/knowledge", {}),
        ("POST", "/api/v1/escalations/run", None),
    ):
        assert client.request(method, path, headers=viewer, json=body).status_code == 403, path


def test_notifications_are_strictly_per_user(client, as_role):
    from config.database import SessionLocal
    from modules.notifications.service import create_notification

    db = SessionLocal()
    try:
        note = create_notification(db, as_role["employee"]["id"], "task_assigned", "Mine only", "/sprints")
        note_id = note.id
    finally:
        db.close()
    other = as_role["manager"]["headers"]
    assert client.post(f"/api/v1/notifications/{note_id}/read", headers=other).status_code == 404
    assert all(n["id"] != note_id for n in client.get("/api/v1/notifications/me", headers=other).json())
    mine = client.get("/api/v1/notifications/me", headers=as_role["employee"]["headers"]).json()
    assert any(n["id"] == note_id for n in mine)


# ------------------------------------------------------------------ resume uploads

def _job(client, headers):
    r = client.post("/api/v1/recruitment/jobs", headers=headers, json={
        "title": "P5 Upload Check", "description": "Security regression job posting for uploads.",
        "required_skills": "python, fastapi",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


GOOD_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def test_resume_upload_rejects_fake_and_oversized_pdfs(client, as_role):
    headers = as_role["recruiter"]["headers"]
    job_id = _job(client, headers)
    url = f"/api/v1/recruitment/jobs/{job_id}/resumes"
    form = {"candidate_name": "P5 Candidate"}

    fake = client.post(url, headers=headers, data=form,
                       files={"resume_file": ("cv.pdf", io.BytesIO(b"MZ\x90 not a pdf"), "application/pdf")})
    assert fake.status_code == 422 and "not a valid PDF" in fake.text

    from modules.recruitment.service import MAX_RESUME_BYTES
    huge = GOOD_PDF + b"0" * (MAX_RESUME_BYTES + 1)
    big = client.post(url, headers=headers, data=form,
                      files={"resume_file": ("big.pdf", io.BytesIO(huge), "application/pdf")})
    assert big.status_code == 422 and "larger than" in big.text

    bulk = client.post(f"{url}/bulk", headers=headers,
                       files=[("files", ("fake.pdf", io.BytesIO(b"hello"), "application/pdf"))])
    assert bulk.status_code in (200, 201), bulk.text
    assert bulk.json()["files"][0]["status"] == "error"


def test_resume_upload_filename_cannot_escape_upload_dir(client, as_role):
    from modules.recruitment.service import UPLOAD_DIR

    headers = as_role["recruiter"]["headers"]
    job_id = _job(client, headers)
    r = client.post(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=headers,
                    data={"candidate_name": "P5 Traversal"},
                    files={"resume_file": ("../../../../p5_escape.pdf", io.BytesIO(GOOD_PDF), "application/pdf")})
    assert r.status_code in (200, 201), r.text
    from config.database import SessionLocal
    from models.resume import Resume
    from core.object_storage import get_object_storage
    from modules.recruitment.service import resume_object_ref

    db = SessionLocal()
    try:
        file_ref = db.get(Resume, r.json()["id"]).file_path
    finally:
        db.close()
    # Resumes now live in object storage: the key must stay a single safe
    # filename under the job's folder, and resolve inside the resumes area.
    bucket, key = resume_object_ref(file_ref)
    folder, _, name = key.partition("/")
    assert folder == f"job_{job_id}"
    assert ".." not in name and "/" not in name and "\\" not in name
    stored = get_object_storage().path_for(bucket, key)  # local backend in tests
    assert UPLOAD_DIR.resolve() in stored.parents
    stored.unlink(missing_ok=True)


# ------------------------------------------------------------------ configuration guards

def test_hosted_deployment_refuses_placeholder_secret_and_disabled_auth(monkeypatch):
    from pydantic import ValidationError
    from config.settings import Settings

    monkeypatch.setenv("RENDER", "true")
    for bad in ("your_jwt_secret_key_here", "unified_ai_enterprise_secret_key_2026", "short"):
        monkeypatch.setenv("SECRET_KEY", bad)
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings()
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    assert Settings().SECRET_KEY == "x" * 48
    monkeypatch.setenv("AUTH_DISABLED", "true")
    with pytest.raises(ValidationError, match="AUTH_DISABLED"):
        Settings()


def test_local_development_only_warns(monkeypatch):
    from config.settings import Settings

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("SECRET_KEY", "your_jwt_secret_key_here")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    s = Settings()
    assert s.AUTH_DISABLED is True


def test_server_errors_do_not_leak_tracebacks(client, as_role, monkeypatch):
    from modules.notifications import service as notification_service

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(notification_service, "unread_counts", boom)
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/notifications/unread-count", headers=as_role["employee"]["headers"])
    assert r.status_code == 500
    assert "secret internal detail" not in r.text and "Traceback" not in r.text
