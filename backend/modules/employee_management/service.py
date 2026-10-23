"""
modules/employee_management/service.py

Business logic for the Employee Management module.

Onboarding creates a User (login account) and Employee (org record)
together in one transaction — the realistic HR flow. There's no email
integration in this app, so the generated temporary password is returned
once in the API response for HR to hand to the new hire directly.
"""

import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from core.security import hash_password
from models.department import Department
from models.employee import Employee
from models.role import Role
from models.user import User


# ------------------------------------------------------------------ #
# Departments
# ------------------------------------------------------------------ #

def list_departments(db: Session) -> list[Department]:
    return db.query(Department).order_by(Department.name).all()


def create_department(db: Session, payload) -> Department:
    existing = db.query(Department).filter(Department.name == payload.name).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A department with this name already exists.")
    dept = Department(name=payload.name, description=payload.description)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


# ------------------------------------------------------------------ #
# Employees
# ------------------------------------------------------------------ #

def _employee_query(db: Session):
    return db.query(Employee).options(
        joinedload(Employee.user).joinedload(User.role),
        joinedload(Employee.department),
    )


def list_employees(db: Session, *, department_id: int | None = None, status_filter: str | None = None) -> list[Employee]:
    query = _employee_query(db).filter(Employee.deleted_at.is_(None))
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if status_filter is not None:
        query = query.filter(Employee.status == status_filter)
    return query.order_by(Employee.created_at.desc()).all()


def get_employee(db: Session, employee_id: int) -> Employee:
    employee = _employee_query(db).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee id={employee_id} not found.")
    return employee


def get_my_employee_record(db: Session, user_id: int) -> Employee:
    employee = _employee_query(db).filter(Employee.user_id == user_id).first()
    if employee is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No employee record yet. Contact HR to be onboarded.",
        )
    return employee


def create_employee(db: Session, payload):
    """Creates the login account + employee record together. Returns
    (Employee, temporary_password)."""
    role = db.query(Role).filter(Role.id == payload.role_id).first()
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Role id={payload.role_id} does not exist.")

    if payload.department_id is not None:
        dept = db.query(Department).filter(Department.id == payload.department_id).first()
        if dept is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Department id={payload.department_id} does not exist.")

    existing_user = (
        db.query(User)
        .filter(User.email == payload.email.lower(), User.deleted_at.is_(None))
        .first()
    )
    if existing_user is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email address already exists.")

    temp_password = secrets.token_urlsafe(9)  # readable-ish, ~12 chars

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hash_password(temp_password),
        role_id=payload.role_id,
        is_active=True,
    )
    db.add(user)
    db.flush()  # populate user.id without committing yet

    employee = Employee(
        user_id=user.id,
        department_id=payload.department_id,
        employee_code=f"EMP-{uuid.uuid4().hex[:8].upper()}",
        job_title=payload.job_title,
        phone=payload.phone,
        hire_date=payload.hire_date,
        employment_type=payload.employment_type,
        status="active",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return get_employee(db, employee.id), temp_password


def update_employee(db: Session, employee_id: int, payload) -> Employee:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee id={employee_id} not found.")

    data = payload.model_dump(exclude_unset=True)
    if "department_id" in data and data["department_id"] is not None:
        dept = db.query(Department).filter(Department.id == data["department_id"]).first()
        if dept is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Department id={data['department_id']} does not exist.")
    for field, value in data.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)
    return get_employee(db, employee.id)


def terminate_employee(db: Session, employee_id: int) -> Employee:
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee id={employee_id} not found.")
    employee.status = "terminated"
    db.commit()
    db.refresh(employee)
    return get_employee(db, employee.id)
