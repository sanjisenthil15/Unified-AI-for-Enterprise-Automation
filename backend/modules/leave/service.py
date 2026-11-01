"""
modules/leave/service.py

Business logic for the Leave Approval workflow (Phase 4.3).

  employee submits  → pending      (approvers notified)
  employee cancels  → cancelled    (pending only)
  approver approves → approved     (attendance days marked on_leave; employee notified)
  approver rejects  → rejected     (reason required; employee notified)

Approvers are Admins and HR Managers. Managers and team leads have no
approval power, and nobody may decide on their own request.

Every transition is one transaction: the status change, attendance
update, notifications, escalation resolution and audit rows commit or
roll back together. Concurrent submissions by the same employee are
serialised by locking their employees row, so two overlapping requests
can't both slip past the overlap check; decisions lock the request row,
so it can't be approved and rejected (or cancelled) at the same time.

Policy assumptions (no approved entitlement policy exists): no leave
balances or accrual; leave types are the fixed LEAVE_TYPES list;
back-dated requests (e.g. sick leave) are allowed; one request may span
at most MAX_SPAN_DAYS calendar days and must contain a working day
(Mon–Fri — the same business-day definition as attendance check-in rates).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from core import audit
from core.permissions import ROLE_ADMIN, ROLE_HR
from models.employee import Employee
from models.leave_request import LEAVE_TYPES, LeaveRequest
from models.role import Role
from models.user import User
from modules.attendance.service import apply_leave_days
from modules.escalations.service import resolve_for_entity
from modules.notifications.service import create_notification, notify_users

APPROVER_ROLES = (ROLE_ADMIN, ROLE_HR)
MAX_SPAN_DAYS = 366
ACTIVE_STATUSES = ("pending", "approved")  # these block overlapping requests


def working_days_between(start: date, end: date) -> int:
    days = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def leave_types() -> dict:
    return {"leave_types": list(LEAVE_TYPES), "max_span_days": MAX_SPAN_DAYS}


def _query(db: Session):
    return db.query(LeaveRequest).options(
        joinedload(LeaveRequest.employee).joinedload(Employee.user),
        joinedload(LeaveRequest.reviewed_by),
    )


def to_response(req: LeaveRequest) -> dict:
    employee = req.employee
    return {
        "id": req.id,
        "employee": {
            "id": employee.id,
            "employee_code": employee.employee_code,
            "job_title": employee.job_title,
            "full_name": employee.user.full_name,
            "email": employee.user.email,
        },
        "leave_type": req.leave_type,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "working_days": req.working_days,
        "reason": req.reason,
        "status": req.status,
        "reviewed_by": (
            {"id": req.reviewed_by.id, "full_name": req.reviewed_by.full_name} if req.reviewed_by else None
        ),
        "reviewed_at": req.reviewed_at,
        "decision_note": req.decision_note,
        "cancelled_at": req.cancelled_at,
        "created_at": req.created_at,
    }


def _get_response(db: Session, request_id: int) -> dict:
    return to_response(_query(db).filter(LeaveRequest.id == request_id).one())


def _approver_user_ids(db: Session, exclude_user_id: int) -> list[int]:
    rows = (
        db.query(User.id)
        .join(Role, User.role_id == Role.id)
        .filter(
            Role.name.in_(APPROVER_ROLES), User.is_active.is_(True), User.deleted_at.is_(None),
            User.id != exclude_user_id,
        )
        .order_by(User.id)
        .all()
    )
    return [r[0] for r in rows]


def _is_approver(user: User) -> bool:
    return getattr(user.role, "name", None) in APPROVER_ROLES


# ------------------------------------------------------------------ #
# Employee actions
# ------------------------------------------------------------------ #

def submit_leave_request(db: Session, employee: Employee, payload) -> dict:
    if employee.status in ("terminated", "inactive") or employee.deleted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inactive or terminated employees cannot request leave.")
    span = (payload.end_date - payload.start_date).days + 1
    if span > MAX_SPAN_DAYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"A single request can cover at most {MAX_SPAN_DAYS} days.",
        )
    working_days = working_days_between(payload.start_date, payload.end_date)
    if working_days == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The selected dates contain no working days (Mon–Fri).")

    # Serialise this employee's submissions so the overlap check below
    # can't race another request being submitted at the same moment.
    db.query(Employee.id).filter(Employee.id == employee.id).with_for_update().one()

    overlap = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee.id,
            LeaveRequest.status.in_(ACTIVE_STATUSES),
            LeaveRequest.start_date <= payload.end_date,
            LeaveRequest.end_date >= payload.start_date,
        )
        .order_by(LeaveRequest.start_date)
        .first()
    )
    if overlap is not None:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"These dates overlap your {overlap.status} request #{overlap.id} "
            f"({overlap.start_date} to {overlap.end_date}).",
        )

    request = LeaveRequest(
        employee_id=employee.id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        working_days=working_days,
        reason=payload.reason,
        status="pending",
    )
    db.add(request)
    audit.label(db, request, "leave_request.submitted")
    db.flush()

    requester = employee.user
    notify_users(
        db, _approver_user_ids(db, exclude_user_id=requester.id), "leave_submitted",
        f"{requester.full_name} requested {payload.leave_type} leave "
        f"({payload.start_date} to {payload.end_date}, {working_days} working day{'s' if working_days != 1 else ''}).",
        "/leave", entity_type="leave_request", entity_id=request.id, dedupe_prefix=f"leave_submitted:{request.id}",
    )
    db.commit()
    return _get_response(db, request.id)


def list_my_requests(db: Session, employee: Employee) -> list[dict]:
    rows = (
        _query(db)
        .filter(LeaveRequest.employee_id == employee.id)
        .order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
        .all()
    )
    return [to_response(r) for r in rows]


def _lock_request(db: Session, request_id: int) -> LeaveRequest:
    request = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Leave request id={request_id} not found.")
    return request


def cancel_leave_request(db: Session, employee: Employee, request_id: int) -> dict:
    request = _lock_request(db, request_id)
    if request.employee_id != employee.id:
        # Same answer as "doesn't exist" — don't reveal other people's requests.
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Leave request id={request_id} not found.")
    if request.status != "pending":
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only pending requests can be cancelled (this one is {request.status}).")
    request.status = "cancelled"
    request.cancelled_at = datetime.now(timezone.utc)
    audit.label(db, request, "leave_request.cancelled")
    resolve_for_entity(db, "leave_request", request.id)
    db.commit()
    return _get_response(db, request.id)


# ------------------------------------------------------------------ #
# Approver actions (Admin / HR Manager)
# ------------------------------------------------------------------ #

def list_requests(
    db: Session, *, status_filter: Optional[str] = None, employee_id: Optional[int] = None, limit: int = 200,
) -> list[dict]:
    query = _query(db)
    if status_filter:
        query = query.filter(LeaveRequest.status == status_filter)
    if employee_id is not None:
        query = query.filter(LeaveRequest.employee_id == employee_id)
    # Oldest pending first is the useful order for a queue; history newest first.
    order = (
        (LeaveRequest.created_at.asc(), LeaveRequest.id.asc()) if status_filter == "pending"
        else (LeaveRequest.created_at.desc(), LeaveRequest.id.desc())
    )
    return [to_response(r) for r in query.order_by(*order).limit(limit).all()]


def _decide(db: Session, reviewer: User, request_id: int, *, approve: bool, note: Optional[str]) -> dict:
    if not _is_approver(reviewer):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Admins and HR Managers can decide on leave requests.")
    request = _lock_request(db, request_id)
    employee = db.query(Employee).options(joinedload(Employee.user)).filter(Employee.id == request.employee_id).one()
    if employee.user_id == reviewer.id:
        db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot decide on your own leave request.")
    if request.status != "pending":
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request has already been {request.status}.")

    request.status = "approved" if approve else "rejected"
    request.reviewed_by_id = reviewer.id
    request.reviewed_at = datetime.now(timezone.utc)
    request.decision_note = note or None
    audit.label(db, request, f"leave_request.{request.status}")

    if approve:
        apply_leave_days(
            db, request.employee_id, request.start_date, request.end_date,
            f"Approved {request.leave_type} leave",
        )
        message = (
            f"Your {request.leave_type} leave ({request.start_date} to {request.end_date}) "
            f"was approved by {reviewer.full_name}."
        )
    else:
        message = (
            f"Your {request.leave_type} leave ({request.start_date} to {request.end_date}) "
            f"was rejected by {reviewer.full_name}: {note}"
        )

    create_notification(
        db, employee.user_id, f"leave_{request.status}", message, "/leave",
        entity_type="leave_request", entity_id=request.id,
        dedupe_key=f"leave_decision:{request.id}", commit=False,
    )
    resolve_for_entity(db, "leave_request", request.id)
    db.commit()
    return _get_response(db, request.id)


def approve_leave_request(db: Session, reviewer: User, request_id: int, note: Optional[str]) -> dict:
    return _decide(db, reviewer, request_id, approve=True, note=note)


def reject_leave_request(db: Session, reviewer: User, request_id: int, reason: str) -> dict:
    return _decide(db, reviewer, request_id, approve=False, note=reason)
