"""
tests/test_auth_hardening.py

Regression test suite for:
1. Public registration policy & /auth/registration-status endpoint
2. Database-backed rate limiting (account+IP, per-account, per-IP, registration per-IP)
3. AuthAttempt privacy (HMAC digests only, no raw PII in auth_attempts)
4. Customer Support persistence:
   - Per-user notification preferences isolation
   - Per-user notification listing & cursor paging
   - Cross-user mark-read authorization (returns 404)
   - Cross-user global search isolation
5. Admin password rotation script (old password fails after rotation)
"""

import hashlib
import hmac
import uuid
import pytest
from datetime import datetime, timezone

from config.settings import settings
from core.rate_limit import _digest
from models.auth_attempt import AuthAttempt
from models.notification import Notification
from models.support_notification_preference import SupportNotificationPreference
from models.user import User
from modules.customer_support import service as cs_service
from scripts.rotate_admin_password import rotate_admin_password


# -----------------------------------------------------------------------------
# 1. Registration Policy Tests
# -----------------------------------------------------------------------------

def test_registration_status_and_closed_policy(client, unique_email, monkeypatch):
    # 1. By default in local dev, registration is enabled
    r = client.get("/api/v1/auth/registration-status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True

    # 2. When disabled via setting (or hosted environment), endpoint reports disabled
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_REGISTRATION", False)
    r = client.get("/api/v1/auth/registration-status")
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    # 3. Registration attempt returns 403 Forbidden
    r_reg = client.post("/api/v1/auth/register", json={
        "full_name": "Closed Reg User",
        "email": unique_email,
        "password": "Str0ngPass1!",
    })
    assert r_reg.status_code == 403
    assert "Self-registration is disabled" in r_reg.json()["detail"]


# -----------------------------------------------------------------------------
# 2. Login & Registration Rate Limiting Tests
# -----------------------------------------------------------------------------

def test_login_rate_limiting_account_ip_lockout(client, unique_email, monkeypatch, db):
    ip = f"198.51.{uuid.uuid4().int % 240 + 10}.{uuid.uuid4().int % 240 + 10}"
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_ACCOUNT_IP", 3)
    headers = {"X-Forwarded-For": ip}
    db.query(AuthAttempt).filter(AuthAttempt.ip_key == _digest(ip)).delete()
    db.commit()

    pw = "Str0ngPass1!"
    client.post("/api/v1/auth/register", headers=headers, json={
        "full_name": "Rate Limit User", "email": unique_email, "password": pw,
    })

    # 3 bad attempts
    for _ in range(3):
        r = client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": "WrongPassword1!"})
        assert r.status_code == 401

    # 4th bad attempt should get 429
    r_locked = client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": "WrongPassword1!"})
    assert r_locked.status_code == 429
    assert "Too many failed sign-in attempts" in r_locked.json()["detail"]
    assert "Retry-After" in r_locked.headers

    # Even a correct password must be refused while locked
    r_corr_locked = client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": pw})
    assert r_corr_locked.status_code == 429


def test_login_rate_limiting_per_ip(client, monkeypatch, db):
    ip = f"198.51.{uuid.uuid4().int % 240 + 10}.{uuid.uuid4().int % 240 + 10}"
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_IP", 3)
    headers = {"X-Forwarded-For": ip}
    db.query(AuthAttempt).filter(AuthAttempt.ip_key == _digest(ip)).delete()
    db.commit()

    # Send bad login requests from this IP with distinct emails
    for i in range(3):
        em = f"pytest_spray_{i}_{uuid.uuid4().hex[:6]}@example.com"
        r = client.post("/api/v1/auth/login", headers=headers, json={"email": em, "password": "WrongPassword1!"})
        assert r.status_code == 401

    # 4th attempt from same IP (even for an arbitrary account) gets 429
    em_new = f"pytest_spray_new_{uuid.uuid4().hex[:6]}@example.com"
    r_ip_lock = client.post("/api/v1/auth/login", headers=headers, json={"email": em_new, "password": "WrongPassword1!"})
    assert r_ip_lock.status_code == 429


def test_login_failures_cleared_on_success(client, unique_email, monkeypatch, db):
    ip = f"198.51.{uuid.uuid4().int % 240 + 10}.{uuid.uuid4().int % 240 + 10}"
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_ACCOUNT_IP", 3)
    headers = {"X-Forwarded-For": ip}
    db.query(AuthAttempt).filter(AuthAttempt.ip_key == _digest(ip)).delete()
    db.commit()

    pw = "Str0ngPass1!"
    client.post("/api/v1/auth/register", headers=headers, json={
        "full_name": "Reset Limit User", "email": unique_email, "password": pw,
    })

    # Fail twice (limit is 3)
    client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": "WrongPassword1!"})
    client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": "WrongPassword1!"})

    # Successful login clears the failures
    r_ok = client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": pw})
    assert r_ok.status_code == 200

    # Next bad login should be attempt 1 again, not 3 (so not locked)
    r_fail = client.post("/api/v1/auth/login", headers=headers, json={"email": unique_email, "password": "WrongPassword1!"})
    assert r_fail.status_code == 401


def test_registration_rate_limiting_per_ip(client, monkeypatch, db):
    ip = f"198.51.{uuid.uuid4().int % 240 + 10}.{uuid.uuid4().int % 240 + 10}"
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "REGISTRATION_MAX_PER_IP", 2)
    headers = {"X-Forwarded-For": ip}
    db.query(AuthAttempt).filter(AuthAttempt.ip_key == _digest(ip)).delete()
    db.commit()

    em1 = f"pytest_reg_lim1_{uuid.uuid4().hex[:6]}@example.com"
    em2 = f"pytest_reg_lim2_{uuid.uuid4().hex[:6]}@example.com"
    em3 = f"pytest_reg_lim3_{uuid.uuid4().hex[:6]}@example.com"

    r1 = client.post("/api/v1/auth/register", headers=headers, json={"full_name": "U1", "email": em1, "password": "Str0ngPass1!"})
    assert r1.status_code == 201

    r2 = client.post("/api/v1/auth/register", headers=headers, json={"full_name": "U2", "email": em2, "password": "Str0ngPass1!"})
    assert r2.status_code == 201

    r3 = client.post("/api/v1/auth/register", headers=headers, json={"full_name": "U3", "email": em3, "password": "Str0ngPass1!"})
    assert r3.status_code == 429
    assert "Too many accounts created from this network" in r3.json()["detail"]


def test_auth_attempts_no_raw_pii_stored(client, db):
    # Check all rows in auth_attempts
    attempts = db.query(AuthAttempt).all()
    for att in attempts:
        if att.account_key is not None:
            # Must be a 64-char sha256 hex string
            assert len(att.account_key) == 64
            assert "@" not in att.account_key
        if att.ip_key is not None:
            assert len(att.ip_key) == 64
            assert "testclient" not in att.ip_key
            assert "." not in att.ip_key


# -----------------------------------------------------------------------------
# 3. Customer Support Persistence & Privacy Tests
# -----------------------------------------------------------------------------

def test_support_preferences_per_user_isolation(client, new_user):
    user_a = new_user("User A", role="employee")
    user_b = new_user("User B", role="employee")

    # User A customizes preferences
    payload_a = {
        "email_notifications": False,
        "ticket_updates": False,
        "sla_alerts": True,
        "incident_alerts": True,
        "agent_replies": False,
    }
    r_up_a = client.put(
        "/api/v1/customer-support/notifications/preferences",
        headers=user_a["headers"],
        json=payload_a,
    )
    assert r_up_a.status_code == 200
    assert r_up_a.json()["ticket_updates"] is False
    assert r_up_a.json()["agent_replies"] is False

    # User B reads preferences -> must still have defaults (all True)
    r_get_b = client.get(
        "/api/v1/customer-support/notifications/preferences",
        headers=user_b["headers"],
    )
    assert r_get_b.status_code == 200
    assert r_get_b.json()["ticket_updates"] is True
    assert r_get_b.json()["agent_replies"] is True
    assert r_get_b.json()["email_notifications"] is True

    # User A reads preferences -> remains isolated
    r_get_a = client.get(
        "/api/v1/customer-support/notifications/preferences",
        headers=user_a["headers"],
    )
    assert r_get_a.status_code == 200
    assert r_get_a.json()["ticket_updates"] is False
    assert r_get_a.json()["agent_replies"] is False


def test_support_notifications_paging_and_ownership(client, db, new_user):
    user_a = new_user("User A Notifs", role="employee")
    user_b = new_user("User B Notifs", role="employee")

    # Add 3 notifications for user A and 1 for user B
    notifs_a = [
        Notification(
            user_id=user_a["id"],
            type="support_ticket_update",
            category="support",
            message=f"Update {i}",
            entity_type="support_ticket",
            entity_id=100 + i,
        )
        for i in range(1, 4)
    ]
    notif_b = Notification(
        user_id=user_b["id"],
        type="support_agent_reply",
        category="support",
        message="User B update",
        entity_type="support_ticket",
        entity_id=200,
    )
    db.add_all(notifs_a + [notif_b])
    db.commit()

    # User A lists notifications
    r_a = client.get("/api/v1/customer-support/notifications", headers=user_a["headers"])
    assert r_a.status_code == 200
    data_a = r_a.json()
    assert data_a["is_live_data"] is True
    assert len(data_a["notifications"]) == 3
    assert data_a["unread_count"] == 3

    # User A tests paging with limit=2
    r_page1 = client.get(
        "/api/v1/customer-support/notifications?limit=2",
        headers=user_a["headers"],
    )
    assert r_page1.status_code == 200
    items_p1 = r_page1.json()["notifications"]
    assert len(items_p1) == 2
    oldest_in_p1 = int(items_p1[-1]["id"])

    # Next page using before_id
    r_page2 = client.get(
        f"/api/v1/customer-support/notifications?limit=2&before_id={oldest_in_p1}",
        headers=user_a["headers"],
    )
    assert r_page2.status_code == 200
    items_p2 = r_page2.json()["notifications"]
    assert len(items_p2) == 1

    # Cross-user authorization: User B cannot mark User A's notification as read
    user_a_nid = notifs_a[0].id
    r_bad_mark = client.post(
        f"/api/v1/customer-support/notifications/{user_a_nid}/read",
        headers=user_b["headers"],
    )
    assert r_bad_mark.status_code == 404

    # User A marks own notification as read
    r_ok_mark = client.post(
        f"/api/v1/customer-support/notifications/{user_a_nid}/read",
        headers=user_a["headers"],
    )
    assert r_ok_mark.status_code == 200


def test_support_global_search_cross_user_isolation(client, new_user):
    user_a = new_user("Search Owner A", role="employee")
    user_b = new_user("Search Visitor B", role="employee")
    admin = new_user("Search Admin", role="admin")

    unique_subject = f"Isolated Issue {uuid.uuid4().hex[:8]}"

    # User A submits a ticket
    r_tkt = client.post(
        "/api/v1/customer-support/tickets",
        headers=user_a["headers"],
        json={
            "subject": unique_subject,
            "description": "Private bug description",
            "priority": "medium",
            "customer_name": "Owner A",
            "customer_email": user_a["email"],
        },
    )
    assert r_tkt.status_code == 201
    tkt_id = r_tkt.json()["id"]

    # User B searches for that unique subject -> MUST NOT find it
    r_search_b = client.get(
        f"/api/v1/customer-support/global-search?q={unique_subject}",
        headers=user_b["headers"],
    )
    assert r_search_b.status_code == 200
    b_ticket_ids = [res["id"] for res in r_search_b.json()["results"] if res["type"] == "ticket"]
    assert f"tkt_{tkt_id}" not in b_ticket_ids

    # User A searches -> DOES find it
    r_search_a = client.get(
        f"/api/v1/customer-support/global-search?q={unique_subject}",
        headers=user_a["headers"],
    )
    assert r_search_a.status_code == 200
    a_ticket_ids = [res["id"] for res in r_search_a.json()["results"] if res["type"] == "ticket"]
    assert f"tkt_{tkt_id}" in a_ticket_ids

    # Admin searches -> DOES find it
    r_search_adm = client.get(
        f"/api/v1/customer-support/global-search?q={unique_subject}",
        headers=admin["headers"],
    )
    assert r_search_adm.status_code == 200
    adm_ticket_ids = [res["id"] for res in r_search_adm.json()["results"] if res["type"] == "ticket"]
    assert f"tkt_{tkt_id}" in adm_ticket_ids


# -----------------------------------------------------------------------------
# 4. Admin Password Rotation Tests
# -----------------------------------------------------------------------------

def test_admin_password_rotation(client, unique_email):
    # Register a test admin
    old_pw = "OldStr0ngPass1!"
    new_pw = "NewStr0ngPass2!"
    client.post("/api/v1/auth/register", json={
        "full_name": "Rotate Target Admin", "email": unique_email, "password": old_pw,
    })

    # Verify old password works
    r_login_old = client.post("/api/v1/auth/login", json={"email": unique_email, "password": old_pw})
    assert r_login_old.status_code == 200

    # Rotate password via rotate_admin_password helper
    success = rotate_admin_password(email=unique_email, new_password=new_pw)
    assert success is True

    # Old password must now fail
    r_login_old2 = client.post("/api/v1/auth/login", json={"email": unique_email, "password": old_pw})
    assert r_login_old2.status_code == 401

    # New password must now succeed
    r_login_new = client.post("/api/v1/auth/login", json={"email": unique_email, "password": new_pw})
    assert r_login_new.status_code == 200
