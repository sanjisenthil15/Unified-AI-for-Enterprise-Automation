"""
modules/attendance/router.py

FastAPI router for the Attendance module.

Endpoints:
    POST /attendance/check-in                     — self check-in (any employee)
    POST /attendance/check-out                     — self check-out (any employee)
    POST /attendance/leave                          — self-declare planned leave (any employee)
    GET  /attendance/me                              — own history (any employee)
    GET  /attendance/team?project_id=                — team view (that project's team lead, or admin/hr_manager)
    GET  /attendance/employee/{employee_id}           — single-employee drill-down (their team lead, or admin/hr_manager)
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.authorization import assert_manager_of, assert_project_manager
from core.dependencies import get_current_employee, get_current_employee_optional, get_current_user
from models.employee import Employee
from models.user import User

from modules.attendance.schemas import AttendanceResponse, EmployeeAttendanceDetail, LeaveRequest, TeamAttendanceEntry
from modules.employee_management.service import get_employee
from modules.attendance import service

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post("/check-in", response_model=AttendanceResponse, summary="Check in for today")
def check_in(
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.check_in(db, current_employee.id)


@router.post("/check-out", response_model=AttendanceResponse, summary="Check out for today")
def check_out(
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.check_out(db, current_employee.id)


@router.post("/leave", response_model=List[AttendanceResponse], summary="Mark planned leave for a date range")
def mark_leave(
    payload: LeaveRequest,
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.mark_leave(db, current_employee.id, payload.start_date, payload.end_date, payload.reason)


@router.get("/me", response_model=List[AttendanceResponse], summary="The caller's own attendance history")
def list_my_attendance(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.list_my_attendance(db, current_employee.id, start_date, end_date)


@router.get("/team", response_model=List[TeamAttendanceEntry], summary="Team attendance (that project's team lead, or admin/hr_manager)")
def list_team_attendance(
    project_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    assert_project_manager(db, current_user, current_employee, project_id)
    return service.list_team_attendance(db, project_id, start_date, end_date)


@router.get("/employee/{employee_id}", response_model=EmployeeAttendanceDetail, summary="Single-employee attendance drill-down (their team lead, or admin/hr_manager)")
def get_employee_attendance(
    employee_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    target_employee = get_employee(db, employee_id)
    assert_manager_of(db, current_user, current_employee, target_employee)
    return service.get_employee_attendance(db, employee_id, start_date, end_date)
