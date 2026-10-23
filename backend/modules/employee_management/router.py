"""
modules/employee_management/router.py

FastAPI router for the Employee Management module.

Endpoints:
    GET    /employee-management/me                   — the caller's own employee record (any user)
    GET    /employee-management/employees             — directory (admin / hr_manager)
    POST   /employee-management/employees             — onboard a new hire (admin / hr_manager)
    GET    /employee-management/employees/{id}        — single employee (admin / hr_manager)
    PATCH  /employee-management/employees/{id}        — update job title/department/status (admin / hr_manager)
    POST   /employee-management/employees/{id}/terminate — mark terminated (admin / hr_manager)
    GET    /employee-management/departments           — list departments (any authenticated user)
    POST   /employee-management/departments           — create a department (admin / hr_manager)
    GET    /employee-management/projects              — list projects + team leads (any authenticated user)
    POST   /employee-management/projects              — create a project (admin / hr_manager)
    POST   /employee-management/projects/{id}/team-lead — assign the team lead (admin / hr_manager)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_employee_optional, get_current_user, require_roles
from models.employee import Employee
from models.user import User

from modules.employee_management.schemas import (
    AssignTeamLead,
    DepartmentCreate,
    DepartmentResponse,
    EmployeeCreate,
    EmployeeCreatedResponse,
    EmployeeResponse,
    EmployeeUpdate,
    ProjectCreate,
    ProjectResponse,
)
from modules.employee_management import service

router = APIRouter(prefix="/employee-management", tags=["Employee Management"])

_MANAGE_ROLES = ["admin", "hr_manager"]


# ------------------------------------------------------------------ #
# Self-service
# ------------------------------------------------------------------ #

@router.get("/me", response_model=EmployeeResponse, summary="The caller's own employee record")
def get_my_record(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_my_employee_record(db, current_user.id)


# ------------------------------------------------------------------ #
# Departments
# ------------------------------------------------------------------ #

@router.get("/departments", response_model=List[DepartmentResponse], summary="List departments")
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_departments(db)


@router.post(
    "/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED,
    summary="Create a department (Admin / HR Manager only)",
)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    return service.create_department(db, payload)


# ------------------------------------------------------------------ #
# Employees
# ------------------------------------------------------------------ #

@router.get(
    "/employees", response_model=List[EmployeeResponse],
    summary="Employee directory (Admin / HR Manager only)",
)
def list_employees(
    department_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    return service.list_employees(db, department_id=department_id, status_filter=status_filter)


@router.post(
    "/employees", response_model=EmployeeCreatedResponse, status_code=status.HTTP_201_CREATED,
    summary="Onboard a new employee — creates their login account too (Admin / HR Manager only)",
)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    employee, temp_password = service.create_employee(db, payload)
    return EmployeeCreatedResponse(employee=employee, temporary_password=temp_password)


@router.get(
    "/employees/{employee_id}", response_model=EmployeeResponse,
    summary="Get a single employee (Admin / HR Manager only)",
)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    return service.get_employee(db, employee_id)


@router.patch(
    "/employees/{employee_id}", response_model=EmployeeResponse,
    summary="Update an employee's job title/department/status (Admin / HR Manager only)",
)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    return service.update_employee(db, employee_id, payload)


@router.post(
    "/employees/{employee_id}/terminate", response_model=EmployeeResponse,
    summary="Mark an employee terminated (Admin / HR Manager only)",
)
def terminate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    return service.terminate_employee(db, employee_id)


# ------------------------------------------------------------------ #
# Projects
# ------------------------------------------------------------------ #

@router.get("/projects", response_model=List[ProjectResponse], summary="List projects and their team leads")
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_projects(db)


@router.post(
    "/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED,
    summary="Create a project (Admin / HR Manager only)",
)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.create_project(db, payload, current_employee)


@router.post(
    "/projects/{project_id}/team-lead", response_model=ProjectResponse,
    summary="Assign a project's team lead — must already be a member of the project (Admin / HR Manager only)",
)
def assign_team_lead(
    project_id: int,
    payload: AssignTeamLead,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(_MANAGE_ROLES)),
):
    return service.assign_team_lead(db, project_id, payload.employee_id)
