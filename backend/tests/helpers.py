"""Shared test helpers (plain functions, not fixtures)."""

FIRST_LOGIN_PASSWORD = "FirstLogin1"


def complete_first_login(client, email, temp_password, new_password=FIRST_LOGIN_PASSWORD):
    """Log in with an HR-issued temporary password and complete the
    mandatory first-login password change. Returns auth headers for the
    fresh session — the temporary-password session can't call app APIs."""
    login = client.post("/api/v1/auth/login", json={"email": email, "password": temp_password})
    assert login.status_code == 200, login.text
    r = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"current_password": temp_password, "new_password": new_password, "confirm_password": new_password},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
