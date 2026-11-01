"""
scripts/run_escalation_sweep.py

Run one escalation sweep and exit — for an external scheduler such as a
Render Cron Job, so escalation checks keep happening even while the web
service is asleep or idle.

Uses the same database lock and throttle as the in-process scheduler
(scheduled_job_runs, FOR UPDATE SKIP LOCKED), so it can safely overlap
with running web workers: at most one sweep runs per interval, and
escalations / notifications are de-duplicated in the database.

Run:
    cd backend && .venv\Scripts\python -m scripts.run_escalation_sweep
    (Render Cron Job command:  python -m scripts.run_escalation_sweep)

Exit code: 0 when the sweep ran or was legitimately skipped, 1 on error.
"""

import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402,F401 — register every mapper before querying
from config.database import SessionLocal  # noqa: E402
from modules.escalations.service import run_sweep_now  # noqa: E402

logger = logging.getLogger("escalation_sweep")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = SessionLocal()
    try:
        result = run_sweep_now(db)
        if result is None:
            logger.info("Skipped: another process is sweeping or a sweep ran within the interval")
        else:
            logger.info("Sweep ran: %s", json.dumps(result))
        return 0
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Escalation sweep failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
