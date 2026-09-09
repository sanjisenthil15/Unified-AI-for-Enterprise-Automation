"""Auth module regression tests (run against PostgreSQL)."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_returns_seeded_role(client, unique_email):
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User",
        "email": unique_email,
        "password": "Str0ngPass1",
        "role_id": 1,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == unique_email
    assert body["role"]["name"] == "admin"


def test_register_rejects_weak_password(client, unique_email):
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User",
        "email": unique_email,
        "password": "alllowercase",  # no uppercase, no digit
        "role_id": 1,
    })
    assert r.status_code == 422


def test_login_and_me(client, unique_email):
    pw = "Str0ngPass1"
    client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User", "email": unique_email, "password": pw, "role_id": 1,
    })
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": pw})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == unique_email


def test_login_rejects_bad_password(client, unique_email):
    client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User", "email": unique_email, "password": "Str0ngPass1", "role_id": 1,
    })
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": "Wr0ngPass1"})
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)
