"""
modules/attendance/service.py

Business logic for the Attendance module.

compute_checkin_rate() is the one place "how reliable has this employee's
attendance been over a date range" is computed — reused unmodified by
the Sprints module's manager-review endpoint.
"""

from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from models.attendance import Attendance
from models.employee import Employee
from models.user import User

DEFAULT_HISTORY_DAYS = 30


def _today() -> date:
    return datetime.utcnow().date()


def _default_range(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end = end_date or _today()
    start = start_date or (end - timedelta(days=DEFAULT_HISTORY_DAYS))
    return start, end


# ------------------------------------------------------------------ #
# Check-in / check-out / leave
# ------------------------------------------------------------------ #

def check_in(db: Session, employee_id: int) -> Attendance:
    today = _today()
    record = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.work_date == today)
        .first()
    )
    if record is not None and record.check_in_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already checked in today.")

    if record is None:
        record = Attendance(employee_id=employee_id, work_date=today, status="present")
        db.add(record)
    record.check_in_at = datetime.utcnow()
    record.status = "present"
    db.commit()
    db.refresh(record)
    return record


def check_out(db: Session, employee_id: int) -> Attendance:
    today = _today()
    record = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.work_date == today)
        .first()
    )
    if record is None or record.check_in_at is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot check out before checking in.")
    if record.check_out_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already checked out today.")

    record.check_out_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return record


def mark_leave(db: Session, employee_id: int, start_date: date, end_date: date, reason: str | None) -> list[Attendance]:
    if end_date < start_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "end_date must be on or after start_date.")

    records = []
    current = start_date
    while current <= end_date:
        existing = (
            db.query(Attendance)
            .filter(Attendance.employee_id == employee_id, Attendance.work_date == current)
            .first()
        )
        if existing is not None and existing.check_in_at is not None:
            # Already worked that day — leave can't retroactively override it.
            current += timedelta(days=1)
            continue
        if existing is None:
            existing = Attendance(employee_id=employee_id, work_date=current)
            db.add(existing)
        existing.status = "on_leave"
        existing.notes = reason
        records.append(existing)
        current += timedelta(days=1)

    db.commit()
    for r in records:
        db.refresh(r)
    return records


# ------------------------------------------------------------------ #
# Reads
# ------------------------------------------------------------------ #

def list_my_attendance(db: Session, employee_id: int, start_date: date | None, end_date: date | None) -> list[Attendance]:
    start, end = _default_range(start_date, end_date)
    return (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.work_date >= start, Attendance.work_date <= end)
        .order_by(Attendance.work_date.desc())
        .all()
    )


def _checkin_rate_from_records(records: list[Attendance], start_date: date, end_date: date) -> float:
    on_leave_dates = {r.work_date for r in records if r.status == "on_leave"}
    checked_in_dates = {r.work_date for r in records if r.check_in_at is not None}

    business_days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in on_leave_dates:
            business_days += 1
        current += timedelta(days=1)

    if business_days == 0:
        return 1.0
    checked_in_business_days = len([d for d in checked_in_dates if d.weekday() < 5])
    return checked_in_business_days / business_days


def compute_checkin_rate(db: Session, employee_id: int, start_date: date, end_date: date) -> float:
    """Fraction of expected business days (Mon-Fri, excluding on_leave days)
    the employee actually checked in on, over [start_date, end_date]."""
    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.work_date >= start_date, Attendance.work_date <= end_date)
        .all()
    )
    return _checkin_rate_from_records(records, start_date, end_date)


def compute_checkin_rates_for_employees(
    db: Session, employee_ids: list[int], start_date: date, end_date: date,
) -> dict[int, float]:
    """Batched compute_checkin_rate — one query for every employee instead
    of one query each. Used by the review/overview endpoints, which
    otherwise N+1 (one round-trip per team member); on a hosted Postgres
    with real network latency per round-trip, that N+1 is the dominant
    cost of loading those pages."""
    if not employee_ids:
        return {}
    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id.in_(employee_ids), Attendance.work_date >= start_date, Attendance.work_date <= end_date)
        .all()
    )
    by_employee: dict[int, list[Attendance]] = {eid: [] for eid in employee_ids}
    for r in records:
        by_employee.setdefault(r.employee_id, []).append(r)
    return {
        eid: _checkin_rate_from_records(recs, start_date, end_date)
        for eid, recs in by_employee.items()
    }


def get_employee_attendance(db: Session, employee_id: int, start_date: date | None, end_date: date | None) -> dict:
    start, end = _default_range(start_date, end_date)
    records = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.work_date >= start, Attendance.work_date <= end)
        .order_by(Attendance.work_date.desc())
        .all()
    )
    return {
        "records": records,
        "checkin_rate": compute_checkin_rate(db, employee_id, start, end),
    }


def _employee_brief(employee: Employee) -> dict:
    return {
        "id": employee.id,
        "user_id": employee.user_id,
        "employee_code": employee.employee_code,
        "job_title": employee.job_title,
        "full_name": employee.user.full_name,
    }


def list_team_attendance(db: Session, project_id: int, start_date: date | None, end_date: date | None) -> list[dict]:
    start, end = _default_range(start_date, end_date)
    members = (
        db.query(Employee)
        .options(joinedload(Employee.user))
        .filter(Employee.project_id == project_id, Employee.deleted_at.is_(None))
        .order_by(Employee.employee_code)
        .all()
    )
    entries = []
    for member in members:
        records = (
            db.query(Attendance)
            .filter(Attendance.employee_id == member.id, Attendance.work_date >= start, Attendance.work_date <= end)
            .order_by(Attendance.work_date.desc())
            .all()
        )
        entries.append({
            "employee": _employee_brief(member),
            "records": records,
            "checkin_rate": compute_checkin_rate(db, member.id, start, end),
        })
    return entries
