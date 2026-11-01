"""
core/dependencies.py

Reusable FastAPI dependency functions for authentication and
role-based access control (RBAC).

How to use in a route:
    # Require any authenticated user
    current_user: User = Depends(get_current_user)

    # Require a specific role (e.g. admin only)
    _: User = Depends(require_roles(["admin"]))

    # Require one of several roles
    _: User = Depends(require_roles(["admin", "hr"]))
"""

from typing import List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from config.database import get_db
from config.settings import settings
from core.audit import set_actor
from core.security import verify_access_token
from models.employee import Employee
from models.user import User

# Bearer token extractor — reads "Authorization: Bearer <token>" header.
# auto_error=False so that, when AUTH_DISABLED is set, requests without a
# token are still allowed through (handled in get_current_user).
_bearer_scheme = HTTPBearer(auto_error=False)


def _dev_user(db: Session) -> User:
    """The seeded demo admin used when AUTH_DISABLED is on."""
    user = (
        db.query(User)
        .filter(User.email == settings.DEV_USER_EMAIL, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "AUTH_DISABLED is set but the demo user is missing. "
                "Run `alembic upgrade head`."
            ),
        )
    return user


# ------------------------------------------------------------------ #
# Core authentication dependency
# ------------------------------------------------------------------ #

# Machine-readable 403 code the frontend uses to route to the mandatory
# Change Password screen (distinct from ordinary permission 403s).
PASSWORD_CHANGE_REQUIRED = "password_change_required"


def _resolve_user(credentials: Optional[HTTPAuthorizationCredentials], db: Session) -> User:
    """
    Validates the JWT and returns the active User it identifies.

    Raises HTTP 401 when:
      - The Authorization header is missing or malformed
      - The token signature is invalid or expired
      - The token payload is missing expected claims
      - No user with the encoded ID exists in the database
      - The token's `ver` no longer matches users.token_version (the
        password was changed or reset after this token was issued)

    Raises HTTP 403 when:
      - The user account is deactivated (is_active = False)
    """
    # Dev bypass — treat every request as the seeded demo admin.
    if settings.AUTH_DISABLED:
        user = _dev_user(db)
        set_actor(user)
        return user

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    # Step 1: Decode and validate the JWT. Tokens issued before session
    # versioning existed carry no `ver` claim and count as version 0, so
    # deploying this doesn't log everyone out.
    try:
        payload = verify_access_token(credentials.credentials)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
        token_version = int(payload.get("ver", 0))
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    # Step 2: Load the user from the database
    user: User | None = (
        db.query(User)
        .filter(User.id == user_id, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise credentials_exception

    # Step 3: Reject sessions revoked by a password change or admin reset
    if token_version != (user.token_version or 0):
        raise credentials_exception

    # Step 4: Ensure the account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact your administrator.",
        )

    # Every audit row written during this request names this user.
    set_actor(user)
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    The standard authentication dependency for every application API.

    In addition to the checks in _resolve_user, accounts still using an
    HR-issued temporary password are blocked with
    403 {"code": "password_change_required"} until they set their own —
    only /auth/me and /auth/change-password (which use
    get_current_user_allow_password_change) remain reachable.
    """
    user = _resolve_user(credentials, db)
    if user.must_change_password and not settings.AUTH_DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": PASSWORD_CHANGE_REQUIRED,
                "message": "You must change your temporary password before continuing.",
            },
        )
    return user


def get_current_user_allow_password_change(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Same authentication as get_current_user, but lets accounts that
    must change their temporary password through. Use ONLY on the routes
    needed to complete that change (/auth/me, /auth/change-password)."""
    return _resolve_user(credentials, db)


# ------------------------------------------------------------------ #
# RBAC dependency factory
# ------------------------------------------------------------------ #

def require_roles(allowed_roles: List[str]):
    """
    Dependency factory that restricts a route to users whose role name
    is in the `allowed_roles` list.

    Usage:
        @router.get("/admin-only")
        def admin_route(_: User = Depends(require_roles(["admin"]))):
            ...

        @router.get("/hr-or-admin")
        def hr_route(_: User = Depends(require_roles(["admin", "hr"]))):
            ...

    Args:
        allowed_roles: List of role name strings that may access the route.

    Returns:
        A FastAPI dependency callable that returns the current user
        if their role is permitted, or raises HTTP 403 otherwise.
    """

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if settings.AUTH_DISABLED:
            return current_user
        if current_user.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role(s): {', '.join(allowed_roles)}. "
                    f"Your role: {current_user.role.name}."
                ),
            )
        return current_user

    return _check


# ------------------------------------------------------------------ #
# Current employee dependency
# ------------------------------------------------------------------ #

def get_current_employee(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Employee:
    """
    Resolves the logged-in User's own Employee record. Used by the
    Attendance / Sprints / Manager Chat modules, which are all scoped to
    "the caller as an employee" rather than just "the caller as a user."

    Raises HTTP 404 if HR hasn't onboarded this account yet (same
    message/shape as employee_management.service.get_my_employee_record).
    """
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No employee record yet. Contact HR to be onboarded.",
        )
    return employee


def get_current_employee_optional(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Optional[Employee]:
    """Like get_current_employee, but returns None instead of 404ing when
    the caller has no Employee record. Used on manager-facing endpoints
    that admin/hr_manager must be able to reach via their role override
    even though they're often not themselves onboarded as an Employee."""
    return db.query(Employee).filter(Employee.user_id == current_user.id).first()
