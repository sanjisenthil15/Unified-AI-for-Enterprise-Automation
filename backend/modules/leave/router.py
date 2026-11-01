"""
modules/leave/router.py

FastAPI router for the Leave Approval module.

Endpoints:
    GET  /leave/types                    — leave types + limits (any user)
    POST /leave/requests                 — submit a request (any onboarded employee)
    GET  /leave/requests/me              — the caller's own requests
    POST /leave/requests/{id}/cancel     — cancel own pending request
    GET  /leave/requests                 — all requests, filterable (Admin / HR Manager)
    POST /leave/requests/{id}/approve    — approve (Admin / HR Manager, never own)
    POST /leave/requests/{id}/reject     — reject with a reason (Admin / HR Manager, never own)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_employee, get_current_user, require_roles
from models.employee import Employee
from models.user import User

from modules.leave.schemas import (
    LeaveApproval, LeaveRejection, LeaveRequestCreate, LeaveRequestResponse, LeaveTypesResponse,
)
from modules.leave import service

router = APIRouter(prefix="/leave", tags=["Leave"])

_APPROVERS = list(service.APPROVER_ROLES)


@router.get("/types", response_model=LeaveTypesResponse, summary="Leave types and request limits")
def get_leave_types(current_user: User = Depends(get_current_user)):
    return service.leave_types()


@router.post(
    "/requests", response_model=LeaveRequestResponse, status_code=status.HTTP_201_CREATED,
    summary="Submit a leave request for approval",
)
def submit_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.submit_leave_request(db, current_employee, payload)


@router.get("/requests/me", response_model=List[LeaveRequestResponse], summary="The caller's own leave requests")
def list_my_leave_requests(
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.list_my_requests(db, current_employee)


@router.post("/requests/{request_id}/cancel", response_model=LeaveRequestResponse, summary="Cancel your own pending request")
def cancel_leave_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_employee: Employee = Depends(get_current_employee),
):
    return service.cancel_leave_request(db, current_employee, request_id)


@router.get(
    "/requests", response_model=List[LeaveRequestResponse],
    summary="All leave requests — approval queue and history (Admin / HR Manager)",
)
def list_leave_requests(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(pending|approved|rejected|cancelled)$"),
    employee_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_APPROVERS)),
):
    return service.list_requests(db, status_filter=status_filter, employee_id=employee_id, limit=limit)


@router.post("/requests/{request_id}/approve", response_model=LeaveRequestResponse, summary="Approve a leave request")
def approve_leave_request(
    request_id: int,
    payload: LeaveApproval,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_APPROVERS)),
):
    return service.approve_leave_request(db, current_user, request_id, payload.note)


@router.post("/requests/{request_id}/reject", response_model=LeaveRequestResponse, summary="Reject a leave request")
def reject_leave_request(
    request_id: int,
    payload: LeaveRejection,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_APPROVERS)),
):
    return service.reject_leave_request(db, current_user, request_id, payload.reason)
