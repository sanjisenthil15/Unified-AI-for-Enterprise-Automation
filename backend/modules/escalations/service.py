"""
modules/escalations/service.py

Escalation rules and the sweep that applies them (Phase 4.4).

Rules (thresholds in config/settings.py):
  leave_pending_overdue   — a leave request still pending after
                            LEAVE_PENDING_ESCALATION_HOURS → every active
                            Admin and HR Manager (except the requester).
  action_items_unreviewed — a project meeting whose AI-proposed action
                            items are still unreviewed after
                            ACTION_ITEM_REVIEW_ESCALATION_HOURS → that
                            project's Manager and Team Lead, or the Admins
                            if it has neither (the people who may review
                            them, 4.2).
Overdue sprint tasks are not a rule here — Sprints already notifies the
team lead once per overdue task (sprints/service._notify_newly_overdue).

Idempotency: an escalation is unique per (rule, entity); recipients'
notifications carry dedupe_key "escalation:<id>:<user>", so re-running
the sweep, retrying after a crash, or two workers racing can't notify
anyone twice. An escalation resolves on the next sweep once its entity
no longer qualifies (and leave decisions resolve theirs immediately).

Triggering: run_sweep_if_due() is called by the in-process scheduler
(modules/escalations/scheduler.py) and, as a backstop, queued as a
background task by GET /notifications/me. Either way it is throttled
through the scheduled_job_runs row, claimed with FOR UPDATE SKIP LOCKED,
so workers / instances share no memory and never double-run it. Admins
can also run it on demand (POST /escalations/run), and
scripts/run_escalation_sweep.py runs it from an external cron.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.database import SessionLocal
from config.settings import settings
from core import audit
from core.permissions import ROLE_ADMIN, ROLE_HR
from models.employee import Employee
from models.escalation import Escalation, ScheduledJobRun
from models.leave_request import LeaveRequest
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.project import Project
from models.role import Role
from models.user import User
from modules.notifications.service import notify_users

logger = logging.getLogger(__name__)

SWEEP_JOB = "escalation_sweep"
RULE_LEAVE_PENDING = "leave_pending_overdue"
RULE_ACTION_ITEMS = "action_items_unreviewed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _active_user_ids_with_roles(db: Session, role_names) -> list[int]:
    rows = (
        db.query(User.id)
        .join(Role, User.role_id == Role.id)
        .filter(Role.name.in_(list(role_names)), User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.id)
        .all()
    )
    return [r[0] for r in rows]


def _open_escalation(
    db: Session, rule: str, entity_type: str, entity_id: int, summary: str,
    recipients: list[int], message: str, link: str,
) -> Optional[Escalation]:
    """Create the escalation and notify its recipients, or do nothing if
    this (rule, entity) was already escalated."""
    exists = (
        db.query(Escalation.id)
        .filter(Escalation.rule == rule, Escalation.entity_type == entity_type, Escalation.entity_id == entity_id)
        .first()
    )
    if exists is not None:
        return None
    escalation = Escalation(rule=rule, entity_type=entity_type, entity_id=entity_id, summary=summary[:255])
    try:
        with db.begin_nested():
            db.add(escalation)
    except IntegrityError:
        return None  # another worker escalated it a moment ago
    escalation.recipient_count = notify_users(
        db, recipients, "escalation", message, link,
        entity_type=entity_type, entity_id=entity_id, dedupe_prefix=f"escalation:{escalation.id}",
    )
    return escalation


def resolve_for_entity(db: Session, entity_type: str, entity_id: int, rule: Optional[str] = None) -> int:
    """Resolve open escalations about an entity inside the caller's
    transaction (never commits)."""
    query = db.query(Escalation).filter(
        Escalation.entity_type == entity_type, Escalation.entity_id == entity_id, Escalation.status == "open",
    )
    if rule:
        query = query.filter(Escalation.rule == rule)
    now = _utcnow()
    count = 0
    for esc in query.all():
        esc.status = "resolved"
        esc.resolved_at = now
        count += 1
    return count


def _sweep_leave(db: Session, now: datetime) -> tuple[int, int]:
    cutoff = now - timedelta(hours=settings.LEAVE_PENDING_ESCALATION_HOURS)
    stale = (
        db.query(LeaveRequest, Employee, User)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .filter(LeaveRequest.status == "pending", LeaveRequest.created_at <= cutoff)
        .order_by(LeaveRequest.id)
        .all()
    )
    approvers = _active_user_ids_with_roles(db, (ROLE_ADMIN, ROLE_HR))
    opened = 0
    for request, _employee, requester in stale:
        recipients = [uid for uid in approvers if uid != requester.id]
        esc = _open_escalation(
            db, RULE_LEAVE_PENDING, "leave_request", request.id,
            f"Leave request #{request.id} from {requester.full_name} pending over "
            f"{settings.LEAVE_PENDING_ESCALATION_HOURS}h",
            recipients,
            f"Escalation: {requester.full_name}'s leave request ({request.start_date} to {request.end_date}) "
            f"has waited over {settings.LEAVE_PENDING_ESCALATION_HOURS}h for a decision.",
            "/leave",
        )
        if esc is not None:
            opened += 1

    resolved = 0
    open_rows = (
        db.query(Escalation, LeaveRequest.status)
        .join(LeaveRequest, LeaveRequest.id == Escalation.entity_id)
        .filter(Escalation.rule == RULE_LEAVE_PENDING, Escalation.status == "open")
        .all()
    )
    for esc, leave_status in open_rows:
        if leave_status != "pending":
            esc.status = "resolved"
            esc.resolved_at = now
            resolved += 1
    return opened, resolved


def _sweep_action_items(db: Session, now: datetime) -> tuple[int, int]:
    cutoff = now - timedelta(hours=settings.ACTION_ITEM_REVIEW_ESCALATION_HOURS)
    stale_meetings = (
        db.query(Meeting, Project)
        .join(Project, Meeting.project_id == Project.id)
        .join(MeetingActionItem, MeetingActionItem.meeting_id == Meeting.id)
        .filter(MeetingActionItem.review_status == "proposed", MeetingActionItem.created_at <= cutoff)
        .distinct()
        .order_by(Meeting.id)
        .all()
    )
    admins = None
    opened = 0
    for meeting, project in stale_meetings:
        # Same people core/authorization.assert_can_review_action_items lets
        # review: the project's Manager and Team Lead, else the Admins.
        recipients = []
        if project.manager_user_id is not None:
            recipients.append(project.manager_user_id)
        if project.team_lead_id is not None:
            lead_user_id = db.query(Employee.user_id).filter(Employee.id == project.team_lead_id).scalar()
            if lead_user_id is not None:
                recipients.append(lead_user_id)
        if not recipients:
            if admins is None:
                admins = _active_user_ids_with_roles(db, (ROLE_ADMIN,))
            recipients = admins
        esc = _open_escalation(
            db, RULE_ACTION_ITEMS, "meeting", meeting.id,
            f"Unreviewed action items in meeting #{meeting.id} ({project.name})",
            recipients,
            f"Escalation: AI-proposed action items from '{meeting.title}' ({project.name}) "
            f"have waited over {settings.ACTION_ITEM_REVIEW_ESCALATION_HOURS}h for review.",
            f"/meetings/offline?meeting={meeting.id}",
        )
        if esc is not None:
            opened += 1

    resolved = 0
    for esc in (
        db.query(Escalation)
        .filter(Escalation.rule == RULE_ACTION_ITEMS, Escalation.status == "open")
        .all()
    ):
        still_pending = (
            db.query(MeetingActionItem.id)
            .filter(MeetingActionItem.meeting_id == esc.entity_id, MeetingActionItem.review_status == "proposed")
            .first()
        )
        if still_pending is None:
            esc.status = "resolved"
            esc.resolved_at = now
            resolved += 1
    return opened, resolved


def run_sweep(db: Session, now: Optional[datetime] = None) -> dict:
    """Apply every rule once inside the caller's transaction (no commit)."""
    now = now or _utcnow()
    leave_opened, leave_resolved = _sweep_leave(db, now)
    items_opened, items_resolved = _sweep_action_items(db, now)
    return {
        "opened": leave_opened + items_opened,
        "resolved": leave_resolved + items_resolved,
        "by_rule": {
            RULE_LEAVE_PENDING: {"opened": leave_opened, "resolved": leave_resolved},
            RULE_ACTION_ITEMS: {"opened": items_opened, "resolved": items_resolved},
        },
        "ran_at": now.isoformat(),
    }


def _claim_job(db: Session, *, force: bool) -> Optional[ScheduledJobRun]:
    """Lock the sweep's bookkeeping row, or return None if another worker
    holds it or (unless force) it ran within the interval."""
    # Commit the (one-time) bookkeeping row on its own, so a racing worker
    # never waits on our uncommitted insert — it should skip, not block.
    db.execute(
        text("INSERT INTO scheduled_job_runs (job_name) VALUES (:job) ON CONFLICT (job_name) DO NOTHING"),
        {"job": SWEEP_JOB},
    )
    db.commit()
    job = (
        db.query(ScheduledJobRun)
        .filter(ScheduledJobRun.job_name == SWEEP_JOB)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    if not force and job.last_run_at is not None:
        if job.last_run_at > _utcnow() - timedelta(seconds=settings.ESCALATION_SWEEP_INTERVAL_SECONDS):
            return None
    return job


def run_sweep_now(db: Session, *, force: bool = False) -> Optional[dict]:
    """Claim, run and commit one sweep. Returns None when skipped."""
    with audit.system_context(SWEEP_JOB):
        job = _claim_job(db, force=force)
        if job is None:
            db.rollback()
            return None
        job.last_run_at = _utcnow()
        result = run_sweep(db)
        db.commit()
        return result


def run_sweep_if_due() -> None:
    """Background-task entry point: own session, never raises."""
    if not settings.ESCALATION_AUTO_SWEEP:
        return
    db = SessionLocal()
    try:
        # Cheap unlocked read first — almost every poll stops here.
        job = db.get(ScheduledJobRun, SWEEP_JOB)
        if job is not None and job.last_run_at is not None and job.last_run_at > _utcnow() - timedelta(
            seconds=settings.ESCALATION_SWEEP_INTERVAL_SECONDS
        ):
            return
        db.rollback()
        result = run_sweep_now(db)
        if result is None:
            logger.debug("Escalation sweep skipped: another worker holds it or it ran recently")
        else:
            logger.info(
                "Escalation sweep ran: %s opened, %s resolved", result["opened"], result["resolved"],
            )
    except Exception:  # noqa: BLE001 — a failed sweep must never break the caller
        db.rollback()
        logger.warning("Escalation sweep failed", exc_info=True)
    finally:
        db.close()


def list_escalations(db: Session, status_filter: Optional[str] = None, limit: int = 100) -> list[Escalation]:
    query = db.query(Escalation)
    if status_filter:
        query = query.filter(Escalation.status == status_filter)
    return query.order_by(Escalation.triggered_at.desc(), Escalation.id.desc()).limit(limit).all()
