"""
modules/employee_management/schemas.py

Pydantic schemas for the Employee Management module.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "intern")
EMPLOYEE_STATUSES = ("active", "inactive", "on_leave", "terminated")


# ------------------------------------------------------------------ #
# Department schemas
# ------------------------------------------------------------------ #

class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# Employee schemas
# ------------------------------------------------------------------ #

class EmployeeCreate(BaseModel):
    """Onboards a new hire: creates their login account and employee
    record together. role_id controls what they can access in the app;
    job_title/department describe their position in the org."""

    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    role_id: int = Field(..., ge=1, description="Role to grant this account (ID from GET /auth/roles)")
    job_title: str = Field(..., min_length=2, max_length=100)
    department_id: Optional[int] = None
    phone: Optional[str] = Field(None, max_length=30)
    hire_date: date
    employment_type: str = Field("full_time", pattern="^(" + "|".join(EMPLOYMENT_TYPES) + ")$")


class EmployeeUpdate(BaseModel):
    job_title: Optional[str] = Field(None, min_length=2, max_length=100)
    department_id: Optional[int] = None
    phone: Optional[str] = Field(None, max_length=30)
    employment_type: Optional[str] = Field(None, pattern="^(" + "|".join(EMPLOYMENT_TYPES) + ")$")
    status: Optional[str] = Field(None, pattern="^(" + "|".join(EMPLOYEE_STATUSES) + ")$")


class EmployeeUserInfo(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool

    model_config = {"from_attributes": True}


class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    job_title: str
    phone: Optional[str] = None
    hire_date: date
    employment_type: str
    status: str
    department: Optional[DepartmentResponse] = None
    user: EmployeeUserInfo
    created_at: datetime

    model_config = {"from_attributes": True}


class EmployeeCreatedResponse(BaseModel):
    """Returned once, right after onboarding — the only time the plaintext
    temporary password is available. There's no email integration in this
    app yet, so HR hands this to the new hire directly."""

    employee: EmployeeResponse
    temporary_password: str
