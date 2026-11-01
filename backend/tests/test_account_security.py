"""Submodule 4.0 — Account Security: first-login password change, password
change API, token-version session revocation, and administrative reset."""
import pytest

from config.settings import settings
from core.permissions import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_HR, ROLE_MANAGER
from core.security import create_access_token
from models.user import User
from tests.helpers import complete_first_login
from tests.test_security_phase1 import _cleanup_test_managers

ME = "/api/v1/auth/me"
CHANGE = "/api/v1/auth/change-password"
EMP_ME = "/api/v1/employee-management/me"
NEW_PW = "BrandNew1Pass"


@pytest.fixture(autouse=True)
def _no_stray_managers():
    # Only one active Manager may exist (Phase 1); keep test managers isolated.
    _cleanup_test_managers()
    yield
    _cleanup_test_managers()


def _role_id(client, headers, name):
    return next(r["id"] for r in client.get("/api/v1/auth/roles", headers=headers).json() if r["name"] == name)


def _onboard(client, admin_headers, email, role=ROLE_EMPLOYEE):
    r = client.post("/api/v1/employee-management/employees", headers=admin_headers, json={
        "full_name": "Account Security", "email": email, "role_id": _role_id(client, admin_headers, role),
        "job_title": "Engineer", "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    return r.json()["temporary_password"], r.json()["employee"]["user"]["id"]


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _change(client, headers, current, new=NEW_PW, confirm=None):
    return client.post(CHANGE, headers=headers, json={
        "current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm,
    })


# --------------------------------------------------------------------- #
# First-login enforcement
# --------------------------------------------------------------------- #

def test_onboarded_employee_is_blocked_until_password_changed(client, new_user, unique_email):
    admin = new_user()
    temp, _ = _onboard(client, admin["headers"], unique_email)

    login = _login(client, unique_email, temp)
    assert login.status_code == 200, "the temporary password must still allow sign-in"
    headers = _bearer(login.json()["access_token"])

    me = client.get(ME, headers=headers)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True

    blocked = client.get(EMP_ME, headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "password_change_required"
    # role-gated routes are blocked the same way (require_roles builds on get_current_user)
    assert client.get("/api/v1/sprints/tasks/me", headers=headers).status_code == 403


def test_successful_change_clears_flag_revokes_old_token_and_issues_new(client, new_user, unique_email):
    admin = new_user()
    temp, _ = _onboard(client, admin["headers"], unique_email)
    old_headers = _bearer(_login(client, unique_email, temp).json()["access_token"])

    r = _change(client, old_headers, temp)
    assert r.status_code == 200, r.text
    new_headers = _bearer(r.json()["access_token"])

    assert client.get(ME, headers=old_headers).status_code == 401, "old session must be revoked"
    me = client.get(ME, headers=new_headers)
    assert me.status_code == 200 and me.json()["must_change_password"] is False
    assert client.get(EMP_ME, headers=new_headers).status_code == 200

    assert _login(client, unique_email, temp).status_code == 401, "temporary password must stop working"
    assert _login(client, unique_email, NEW_PW).status_code == 200


def test_normal_password_change_for_regular_user(client, new_user):
    user = new_user(role=ROLE_EMPLOYEE)
    r = _change(client, user["headers"], "Str0ngPass1")
    assert r.status_code == 200, r.text
    assert client.get(ME, headers=user["headers"]).status_code == 401
    assert client.get(ME, headers=_bearer(r.json()["access_token"])).status_code == 200
    assert _login(client, user["email"], NEW_PW).status_code == 200


# --------------------------------------------------------------------- #
# Password change failures (none of them change any state)
# --------------------------------------------------------------------- #

@pytest.mark.parametrize("current, new, confirm, status, fragment", [
    ("WrongPass1", NEW_PW, None, 400, "incorrect"),
    ("__TEMP__", "__TEMP__", None, None, None),           # reuse — status asserted below
    ("__TEMP__", NEW_PW, "Mismatch1X", 422, "do not match"),
    ("__TEMP__", "nouppercase1", None, 422, "uppercase"),
    ("__TEMP__", "NoDigitsHere", None, 422, "digit"),
    ("__TEMP__", "Sh0rt", None, 422, "at least 8"),
    ("__TEMP__", "A1" + "é" * 36, None, 422, "72 bytes"),   # 38 chars but 74 UTF-8 bytes
])
def test_change_password_rejections_leave_state_untouched(client, new_user, unique_email, current, new, confirm, status, fragment):
    admin = new_user()
    temp, _ = _onboard(client, admin["headers"], unique_email)
    headers = _bearer(_login(client, unique_email, temp).json()["access_token"])
    current = temp if current == "__TEMP__" else current
    new = temp if new == "__TEMP__" else new

    r = _change(client, headers, current, new, confirm)
    if new == temp:
        # the temporary password itself violates the policy or is a reuse — either way rejected
        assert r.status_code in (400, 422), r.text
    else:
        assert r.status_code == status, r.text
        assert fragment in r.text.lower()

    me = client.get(ME, headers=headers)
    assert me.status_code == 200, "a rejected change must not revoke the session"
    assert me.json()["must_change_password"] is True


def test_password_reuse_rejected(client, new_user):
    user = new_user(role=ROLE_EMPLOYEE)
    r = _change(client, user["headers"], "Str0ngPass1", "Str0ngPass1")
    assert r.status_code == 400
    assert "different" in r.json()["detail"]


def test_change_password_requires_authentication(client):
    assert client.post(CHANGE, json={"current_password": "x", "new_password": NEW_PW, "confirm_password": NEW_PW}).status_code == 401


# --------------------------------------------------------------------- #
# Existing-account compatibility
# --------------------------------------------------------------------- #

def test_self_registered_and_existing_accounts_are_not_forced(client, new_user):
    user = new_user(role=ROLE_EMPLOYEE)
    me = client.get(ME, headers=user["headers"])
    assert me.json()["must_change_password"] is False
    assert client.get("/api/v1/sprints/tasks/me", headers=user["headers"]).status_code != 403


def test_token_without_version_claim_is_version_zero(client, new_user):
    """Sessions issued before this release carry no `ver` claim; they stay
    valid until the password changes, then stop working."""
    user = new_user(role=ROLE_EMPLOYEE)
    legacy = _bearer(create_access_token({"sub": str(user["id"])}))
    assert client.get(ME, headers=legacy).status_code == 200
    assert _change(client, user["headers"], "Str0ngPass1").status_code == 200
    assert client.get(ME, headers=legacy).status_code == 401


def test_forged_future_version_rejected(client, new_user):
    user = new_user(role=ROLE_EMPLOYEE)
    forged = _bearer(create_access_token({"sub": str(user["id"]), "ver": 99}))
    assert client.get(ME, headers=forged).status_code == 401


# --------------------------------------------------------------------- #
# Administrative reset
# --------------------------------------------------------------------- #

def _reset(client, headers, user_id):
    return client.post(f"/api/v1/auth/users/{user_id}/reset-password", headers=headers)


@pytest.mark.parametrize("requester, target, expected", [
    (ROLE_ADMIN, ROLE_EMPLOYEE, 200),
    (ROLE_ADMIN, ROLE_HR, 200),
    (ROLE_ADMIN, ROLE_MANAGER, 200),
    (ROLE_ADMIN, ROLE_ADMIN, 403),
    (ROLE_HR, ROLE_EMPLOYEE, 200),
    (ROLE_HR, ROLE_ADMIN, 403),
    (ROLE_HR, ROLE_MANAGER, 403),
    (ROLE_HR, ROLE_HR, 403),
    (ROLE_EMPLOYEE, ROLE_EMPLOYEE, 403),
    (ROLE_EMPLOYEE, ROLE_ADMIN, 403),
    (ROLE_MANAGER, ROLE_EMPLOYEE, 403),
])
def test_admin_reset_permission_matrix(client, new_user, requester, target, expected):
    actor = new_user("Reset Actor", role=requester)
    victim = new_user("Reset Target", role=target)
    r = _reset(client, actor["headers"], victim["id"])
    assert r.status_code == expected, r.text
    if expected == 200:
        assert r.json()["temporary_password"]
        assert r.json()["must_change_password"] is True
    else:
        # a refused reset leaves the target's session and password untouched
        assert client.get(ME, headers=victim["headers"]).status_code == 200
        assert _login(client, victim["email"], "Str0ngPass1").status_code == 200


def test_admin_reset_forces_change_revokes_sessions_and_records_actor(client, new_user, db):
    admin = new_user()
    victim = new_user("Forgetful", role=ROLE_EMPLOYEE)

    r = _reset(client, admin["headers"], victim["id"])
    assert r.status_code == 200, r.text
    temp = r.json()["temporary_password"]

    assert client.get(ME, headers=victim["headers"]).status_code == 401, "existing sessions revoked"
    assert _login(client, victim["email"], "Str0ngPass1").status_code == 401, "old password no longer works"
    login = _login(client, victim["email"], temp)
    assert login.status_code == 200
    blocked = client.get(EMP_ME, headers=_bearer(login.json()["access_token"]))
    assert blocked.json()["detail"]["code"] == "password_change_required"

    db.expire_all()
    row = db.get(User, victim["id"])
    assert row.password_reset_by_id == admin["id"]
    assert row.password_reset_at is not None
    assert row.must_change_password is True

    # completing the forced change works with the reset password
    complete_first_login(client, victim["email"], temp, new_password="AfterReset1")
    assert _login(client, victim["email"], "AfterReset1").status_code == 200


def test_admin_cannot_reset_self_and_unknown_user_is_404(client, new_user):
    admin = new_user()
    assert _reset(client, admin["headers"], admin["id"]).status_code == 400
    assert _reset(client, admin["headers"], 999_999_999).status_code == 404


def test_temporary_passwords_never_exposed_by_employee_apis(client, new_user, unique_email):
    admin = new_user()
    temp, user_id = _onboard(client, admin["headers"], unique_email)
    reset_temp = _reset(client, admin["headers"], user_id).json()["temporary_password"]
    listing = client.get("/api/v1/employee-management/employees", headers=admin["headers"]).text
    users = client.get("/api/v1/auth/users", headers=admin["headers"]).text
    for secret in (temp, reset_temp):
        assert secret not in listing and secret not in users
    assert "hashed_password" not in listing and "hashed_password" not in users


# --------------------------------------------------------------------- #
# Registration password length & dev mode
# --------------------------------------------------------------------- #

def test_registration_enforces_72_byte_limit_without_truncation(client, unique_email):
    too_long = "A1" + "x" * 71                       # 73 bytes
    r = client.post("/api/v1/auth/register", json={"full_name": "Long Pw", "email": unique_email, "password": too_long})
    assert r.status_code == 422 and "72 bytes" in r.text

    exactly = "A1" + "x" * 70                        # 72 bytes — the maximum
    r = client.post("/api/v1/auth/register", json={"full_name": "Long Pw", "email": unique_email, "password": exactly})
    assert r.status_code == 201, r.text
    assert _login(client, unique_email, exactly).status_code == 200


def test_auth_disabled_dev_mode_unaffected(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_DISABLED", True)
    me = client.get(ME)
    assert me.status_code == 200 and me.json()["email"] == "demo@demo.com"
    assert client.get("/api/v1/sprints/overview").status_code == 200
