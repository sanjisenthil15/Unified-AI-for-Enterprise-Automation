"""Phase 5.3 — server-side escalation scheduler: thresholds, recipients,
closure, failure handling, and genuine concurrent-execution safety
(parallel threads, each with its own DB connection and transaction)."""
import asyncio
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from config.database import SessionLocal, engine
from config.settings import settings
from models.escalation import Escalation
from models.leave_request import LeaveRequest
from models.notification import Notification
from modules.escalations import scheduler, service
from tests.helpers import complete_first_login

EMP_BASE = "/api/v1/employee-management"
REQUESTS = "/api/v1/leave/requests"


def _email(tag):
    return f"pytest_{tag}_{uuid.uuid4().hex[:8]}@example.com"


def _onboard(client, admin_headers, role="employee"):
    email = _email("sch")
    roles = client.get("/api/v1/auth/roles", headers=admin_headers).json()
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": f"Sched {role}", "email": email,
        "role_id": next(x["id"] for x in roles if x["name"] == role),
        "job_title": "Engineer", "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    headers = complete_first_login(client, email, r.json()["temporary_password"])
    return {"user_id": r.json()["employee"]["user"]["id"], "employee_id": r.json()["employee"]["id"], "headers": headers}


def _pending_request(client, emp, hours_old, start="2027-05-03"):
    r = client.post(REQUESTS, headers=emp["headers"], json={
        "leave_type": "annual", "start_date": start, "end_date": start, "reason": "Scheduler test",
    })
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    db = SessionLocal()
    try:
        db.get(LeaveRequest, request_id).created_at = datetime.now(timezone.utc) - timedelta(hours=hours_old)
        db.commit()
    finally:
        db.close()
    return request_id


def _escalations(request_id):
    db = SessionLocal()
    try:
        return db.query(Escalation).filter(
            Escalation.entity_type == "leave_request", Escalation.entity_id == request_id,
        ).all()
    finally:
        db.close()


def _notified_users(request_id):
    db = SessionLocal()
    try:
        rows = db.query(Notification.user_id).filter(
            Notification.type == "escalation", Notification.entity_type == "leave_request",
            Notification.entity_id == request_id,
        ).all()
        return [r[0] for r in rows]
    finally:
        db.close()


def _sweep():
    db = SessionLocal()
    try:
        result = service.run_sweep(db)
        db.commit()
        return result
    finally:
        db.close()


def _reset_job_row():
    with engine.begin() as conn:
        conn.execute(text("UPDATE scheduled_job_runs SET last_run_at = NULL WHERE job_name = :j"),
                     {"j": service.SWEEP_JOB})


def test_threshold_boundary(client, new_user):
    admin = new_user("Sched Admin")
    emp = _onboard(client, admin["headers"])
    fresh = _pending_request(client, emp, settings.LEAVE_PENDING_ESCALATION_HOURS - 1, start="2027-05-03")
    stale = _pending_request(client, emp, settings.LEAVE_PENDING_ESCALATION_HOURS + 1, start="2027-05-04")
    _sweep()
    assert _escalations(fresh) == []
    assert len(_escalations(stale)) == 1


def test_recipients_are_active_approvers_except_requester(client, new_user):
    admin = new_user("Sched Admin")
    hr = _onboard(client, admin["headers"], role="hr_manager")
    inactive_hr = _onboard(client, admin["headers"], role="hr_manager")
    assert client.post(f"{EMP_BASE}/employees/{inactive_hr['employee_id']}/terminate",
                       headers=admin["headers"]).status_code == 200
    manager = _onboard(client, admin["headers"], role="manager")
    requester_hr = _onboard(client, admin["headers"], role="hr_manager")

    request_id = _pending_request(client, requester_hr, settings.LEAVE_PENDING_ESCALATION_HOURS + 2)
    _sweep()
    notified = _notified_users(request_id)
    assert admin["id"] in notified and hr["user_id"] in notified
    assert requester_hr["user_id"] not in notified   # never escalated to the requester
    assert inactive_hr["user_id"] not in notified     # deactivated accounts are skipped
    assert manager["user_id"] not in notified         # managers don't approve leave
    assert len(notified) == len(set(notified))


def test_cancelled_request_closes_its_escalation(client, new_user):
    admin = new_user("Sched Admin")
    emp = _onboard(client, admin["headers"])
    request_id = _pending_request(client, emp, settings.LEAVE_PENDING_ESCALATION_HOURS + 1)
    _sweep()
    assert _escalations(request_id)[0].status == "open"
    assert client.post(f"{REQUESTS}/{request_id}/cancel", headers=emp["headers"]).status_code == 200
    assert _escalations(request_id)[0].status == "resolved"


def test_concurrent_sweeps_without_the_job_lock_still_never_duplicate(client, new_user):
    """Eight sweeps race on separate connections, bypassing the job-row
    lock entirely — the unique (rule, entity) constraint and notification
    dedupe keys alone must keep it to one escalation, one notice each."""
    admin = new_user("Sched Admin")
    hr = _onboard(client, admin["headers"], role="hr_manager")
    emp = _onboard(client, admin["headers"])
    request_id = _pending_request(client, emp, settings.LEAVE_PENDING_ESCALATION_HOURS + 3)

    barrier = threading.Barrier(8)
    errors = []

    def race():
        db = SessionLocal()
        try:
            barrier.wait()
            service.run_sweep(db)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
            db.rollback()
        finally:
            db.close()

    threads = [threading.Thread(target=race) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == []
    assert len(_escalations(request_id)) == 1
    notified = _notified_users(request_id)
    assert notified.count(admin["id"]) == 1
    assert notified.count(hr["user_id"]) == 1


def test_concurrent_scheduler_ticks_run_exactly_one_sweep(new_user):
    """Eight workers tick at the same instant: the FOR UPDATE SKIP LOCKED
    claim plus the last_run_at throttle let exactly one of them sweep."""
    _reset_job_row()
    barrier = threading.Barrier(8)
    results = []
    lock = threading.Lock()

    def tick():
        db = SessionLocal()
        try:
            barrier.wait()
            outcome = service.run_sweep_now(db)
            with lock:
                results.append(outcome)
        finally:
            db.close()

    threads = [threading.Thread(target=tick) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert len(results) == 8
    assert sum(r is not None for r in results) == 1, results


def test_scheduler_loop_triggers_sweep_and_survives_failures(monkeypatch):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(service, "run_sweep_if_due", flaky)

    async def run_briefly():
        task = asyncio.create_task(scheduler.run_scheduler(interval_seconds=0.02, startup_delay=0))
        await asyncio.sleep(0.5)
        await scheduler.stop(task)
        return task

    task = asyncio.run(run_briefly())
    assert len(calls) >= 3          # kept ticking after the first tick raised
    assert task.cancelled()         # and shut down cleanly when cancelled


def test_scheduler_escalates_without_any_browser(client, new_user, monkeypatch):
    """End to end: no HTTP polling at all — only the scheduler loop runs,
    and the stale request gets escalated."""
    admin = new_user("Sched Admin")
    emp = _onboard(client, admin["headers"])
    request_id = _pending_request(client, emp, settings.LEAVE_PENDING_ESCALATION_HOURS + 1)
    _reset_job_row()
    monkeypatch.setattr(settings, "ESCALATION_AUTO_SWEEP", True)
    monkeypatch.setattr(settings, "ESCALATION_SWEEP_INTERVAL_SECONDS", 0)

    async def run_briefly():
        task = asyncio.create_task(scheduler.run_scheduler(interval_seconds=0.05, startup_delay=0))
        for _ in range(100):
            await asyncio.sleep(0.1)
            if _escalations(request_id):
                break
        await scheduler.stop(task)

    asyncio.run(run_briefly())
    assert len(_escalations(request_id)) == 1
    assert admin["id"] in _notified_users(request_id)


def test_scheduler_start_respects_settings(monkeypatch):
    started = []
    monkeypatch.setattr(settings, "ESCALATION_SCHEDULER_ENABLED", False)
    assert scheduler.start(loop_factory=lambda coro: started.append(coro)) is None
    monkeypatch.setattr(settings, "ESCALATION_SCHEDULER_ENABLED", True)
    monkeypatch.setattr(settings, "ESCALATION_AUTO_SWEEP", True)
    scheduler.start(loop_factory=lambda coro: started.append(coro) or "task")
    assert len(started) == 1
    started[0].close()  # never scheduled; avoid an un-awaited coroutine warning
