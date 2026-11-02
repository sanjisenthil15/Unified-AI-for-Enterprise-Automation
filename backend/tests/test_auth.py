"""Auth module regression tests (run against PostgreSQL)."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_always_assigns_employee_role(client, unique_email):
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User",
        "email": unique_email,
        "password": "Str0ngPass1",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == unique_email
    assert body["role"]["name"] == "employee"


def test_register_ignores_a_client_supplied_role_id(client, unique_email):
    # Self-serve registration must never let a caller grant themselves a
    # privileged role — role_id=1 ("admin") here must be silently ignored.
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User",
        "email": unique_email,
        "password": "Str0ngPass1",
        "role_id": 1,
    })
    assert r.status_code == 201, r.text
    assert r.json()["role"]["name"] == "employee"


def test_register_rejects_weak_password(client, unique_email):
    r = client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User",
        "email": unique_email,
        "password": "alllowercase",  # no uppercase, no digit
    })
    assert r.status_code == 422


def test_login_and_me(client, unique_email):
    pw = "Str0ngPass1"
    client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User", "email": unique_email, "password": pw,
    })
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": pw})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == unique_email


def test_login_rejects_bad_password(client, unique_email):
    client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User", "email": unique_email, "password": "Str0ngPass1",
    })
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": "Wr0ngPass1"})
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code in (401, 403)


def test_roles_is_public(client):
    r = client.get("/api/v1/auth/roles")
    assert r.status_code == 200
    names = {role["name"] for role in r.json()}
    assert {"admin", "employee"} <= names


def test_users_lists_active_accounts(client, unique_email):
    pw = "Str0ngPass1"
    client.post("/api/v1/auth/register", json={
        "full_name": "Pytest User", "email": unique_email, "password": pw,
    })
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": pw})
    token = r.json()["access_token"]

    r = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert unique_email in {u["email"] for u in r.json()}

    assert client.get("/api/v1/auth/users").status_code in (401, 403)

def test_register_customer_assigns_customer_role(client, unique_email):
    r = client.post("/api/v1/auth/register-customer", json={
        "full_name": "Customer User",
        "email": unique_email,
        "password": "Str0ngPass1",
        "confirm_password": "Str0ngPass1",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == unique_email
    assert body["role"]["name"] == "customer"


def test_register_customer_password_mismatch(client, unique_email):
    r = client.post("/api/v1/auth/register-customer", json={
        "full_name": "Customer User",
        "email": unique_email,
        "password": "Str0ngPass1",
        "confirm_password": "DifferentPass1",
    })
    assert r.status_code == 422


def test_customer_login_and_token(client, unique_email):
    pw = "Str0ngPass1"
    client.post("/api/v1/auth/register-customer", json={
        "full_name": "Customer User",
        "email": unique_email,
        "password": pw,
        "confirm_password": pw,
    })
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": pw})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"]["name"] == "customer"


def test_customer_blocked_from_internal_modules(client, unique_email):
    pw = "Str0ngPass1"
    client.post("/api/v1/auth/register-customer", json={
        "full_name": "Customer User",
        "email": unique_email,
        "password": pw,
        "confirm_password": pw,
    })
    token = client.post("/api/v1/auth/login", json={"email": unique_email, "password": pw}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for path in [
        "/api/v1/incidents",
        "/api/v1/incidents/teams",
        "/api/v1/meetings",
        "/api/v1/employee-management/projects",
        "/api/v1/chat/contacts",
        "/api/v1/meetings/online/mine",
    ]:
        assert client.get(path, headers=headers).status_code == 403, path

    # Customer support and the customer's own notifications stay reachable.
    assert client.get("/api/v1/customer-support/tickets", headers=headers).status_code == 200
    assert client.get("/api/v1/notifications/unread-count", headers=headers).status_code == 200

