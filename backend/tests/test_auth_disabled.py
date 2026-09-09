"""
AUTH_DISABLED dev mode: when set, every request runs as the seeded demo
admin and role checks are skipped. Default (off) behaviour is unchanged.
"""

import io

import pytest

from config.settings import settings


@pytest.fixture
def auth_off(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_DISABLED", True)


def test_default_mode_still_requires_a_token(client):
    assert settings.AUTH_DISABLED is False
    assert client.get("/api/v1/meetings").status_code in (401, 403)
    assert client.get("/api/v1/auth/me").status_code in (401, 403)


def test_disabled_lets_unauthenticated_requests_through(client, auth_off):
    r = client.get("/api/v1/meetings")            # no Authorization header
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "demo@demo.com"
    assert me.json()["role"]["name"] == "admin"


def test_disabled_skips_role_checks(client, auth_off, db):
    # recruitment job creation normally needs the hr/admin role + a token
    r = client.post("/api/v1/recruitment/jobs", json={
        "title": "Auth-off role check",
        "description": "created without a token",
        "required_skills": "Python",
        "min_education": "Bachelor's Degree",
        "experience_level": "mid",
    })
    assert r.status_code == 201, r.text
    from sqlalchemy import text
    db.execute(text("DELETE FROM job_postings WHERE id = :i"), {"i": r.json()["id"]})
    db.commit()


def test_disabled_full_meeting_flow_without_login(client, auth_off, monkeypatch):
    monkeypatch.setattr("modules.meeting_intelligence.router.run_meeting_pipeline", lambda mid, **kw: None)
    r = client.post(
        "/api/v1/meetings",
        data={"title": "No-login upload"},
        files={"file": ("clip.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"x" * 2048), "video/mp4")},
    )
    assert r.status_code == 201
    mid = r.json()["id"]
    assert client.get(f"/api/v1/meetings/{mid}").status_code == 200
    assert client.delete(f"/api/v1/meetings/{mid}").status_code == 204
