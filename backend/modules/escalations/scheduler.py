"""
modules/escalations/scheduler.py

Server-side trigger for the escalation sweep (Phase 5.3), so escalation
checks no longer depend on a browser polling notifications.

Architecture
  - One asyncio task per worker process, started from main.py's lifespan.
    Every ESCALATION_SCHEDULER_INTERVAL_SECONDS it calls
    service.run_sweep_if_due() in a worker thread (DB work is synchronous).
  - Workers / instances coordinate only through Postgres: run_sweep_now()
    claims the scheduled_job_runs row with FOR UPDATE SKIP LOCKED and
    honours its last_run_at throttle, so however many processes tick, one
    sweep runs per interval. Nothing relies on in-process memory or locks.
  - Escalations are unique per (rule, entity) and recipients' notifications
    carry dedupe keys, so even overlapping sweeps can't duplicate anything.
  - Any exception is logged and the loop carries on; it never takes the
    app down. Cancellation on shutdown is clean.

Deployment note: on Render's free plan the web service sleeps after ~15
minutes without HTTP traffic and no code runs while it sleeps; the first
tick after it wakes catches up on anything that went overdue meanwhile.
For checks that keep running while the web service is idle, schedule
`python -m scripts.run_escalation_sweep` (a Render Cron Job — a paid
Render service — or any external scheduler); it uses the same DB lock.
"""

import asyncio
import logging
import random

from config.settings import settings
from modules.escalations import service

logger = logging.getLogger(__name__)


def _ensure_log_output() -> None:
    """Uvicorn only configures its own loggers, so INFO lines from app
    modules would be dropped. Give the escalations package (scheduler +
    sweep) its own stderr handler — scoped to it on purpose, rather than
    turning on INFO for every library (some log full request URLs)."""
    package_logger = logging.getLogger("modules.escalations")
    if not package_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        package_logger.addHandler(handler)
        package_logger.setLevel(logging.INFO)
        package_logger.propagate = False


# First tick shortly after startup, so a freshly woken instance catches up.
STARTUP_DELAY_SECONDS = 30


async def run_scheduler(interval_seconds: float | None = None, startup_delay: float | None = None) -> None:
    """Loop forever (until cancelled), triggering the throttled sweep."""
    interval = interval_seconds if interval_seconds is not None else settings.ESCALATION_SCHEDULER_INTERVAL_SECONDS
    delay = startup_delay if startup_delay is not None else STARTUP_DELAY_SECONDS
    logger.info("Escalation scheduler started (every %ss)", interval)
    try:
        await asyncio.sleep(delay)
        while True:
            try:
                await asyncio.to_thread(service.run_sweep_if_due)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — keep ticking whatever happens
                logger.exception("Escalation scheduler tick failed")
            # Small jitter so many workers started together don't all hit
            # the lock row in the same instant.
            await asyncio.sleep(interval + random.uniform(0, min(5.0, interval * 0.1)))
    except asyncio.CancelledError:
        logger.info("Escalation scheduler stopped")
        raise


def start(loop_factory=asyncio.create_task) -> asyncio.Task | None:
    """Start the scheduler task if enabled; returns it so lifespan can cancel it."""
    _ensure_log_output()
    if not (settings.ESCALATION_SCHEDULER_ENABLED and settings.ESCALATION_AUTO_SWEEP):
        logger.info("Escalation scheduler disabled by settings")
        return None
    return loop_factory(run_scheduler())


async def stop(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
