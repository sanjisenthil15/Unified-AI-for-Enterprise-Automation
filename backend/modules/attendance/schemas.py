"""
modules/attendance/schemas.py

Pydantic schemas for the Attendance module.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

ATTENDANCE_STATUSES = ("present", "late", "absent", "on_leave")


class AttendanceResponse(BaseModel):
    id: int
    employee_id: int
    work_date: date
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    status: str
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class LeaveRequest(BaseModel):
    start_date: date
    end_date: date
    reason: Optional[str] = Field(None, max_length=255)


class EmployeeBriefInfo(BaseModel):
    id: int
    user_id: int
    employee_code: str
    job_title: str
    full_name: str

    model_config = {"from_attributes": True}


class TeamAttendanceEntry(BaseModel):
    employee: EmployeeBriefInfo
    records: list[AttendanceResponse]
    checkin_rate: float


class EmployeeAttendanceDetail(BaseModel):
    records: list[AttendanceResponse]
    checkin_rate: float
