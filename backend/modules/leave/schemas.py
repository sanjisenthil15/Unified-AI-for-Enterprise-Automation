"""
modules/leave/schemas.py

Pydantic schemas for the Leave Approval module.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.leave_request import LEAVE_TYPES

_TYPE_PATTERN = "^(" + "|".join(LEAVE_TYPES) + ")$"


def _stripped(value: Optional[str]) -> Optional[str]:
    return value.strip() if isinstance(value, str) else value


class LeaveRequestCreate(BaseModel):
    leave_type: str = Field(..., pattern=_TYPE_PATTERN)
    start_date: date
    end_date: date
    reason: str = Field(..., max_length=500)

    _strip_reason = field_validator("reason", mode="before")(_stripped)

    @model_validator(mode="after")
    def _check(self):
        if len(self.reason) < 3:
            raise ValueError("Please give a reason (at least 3 characters).")
        if self.end_date < self.start_date:
            raise ValueError("The end date must be on or after the start date.")
        return self


class LeaveApproval(BaseModel):
    note: Optional[str] = Field(None, max_length=500)

    _strip_note = field_validator("note", mode="before")(_stripped)


class LeaveRejection(BaseModel):
    reason: str = Field(..., max_length=500)

    _strip_reason = field_validator("reason", mode="before")(_stripped)

    @model_validator(mode="after")
    def _check(self):
        if len(self.reason) < 3:
            raise ValueError("A rejection reason is required (at least 3 characters).")
        return self


class LeaveEmployeeInfo(BaseModel):
    id: int
    employee_code: str
    job_title: str
    full_name: str
    email: str


class LeaveReviewerInfo(BaseModel):
    id: int
    full_name: str


class LeaveRequestResponse(BaseModel):
    id: int
    employee: LeaveEmployeeInfo
    leave_type: str
    start_date: date
    end_date: date
    working_days: int
    reason: str
    status: str
    reviewed_by: Optional[LeaveReviewerInfo] = None
    reviewed_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime


class LeaveTypesResponse(BaseModel):
    leave_types: list[str]
    max_span_days: int
