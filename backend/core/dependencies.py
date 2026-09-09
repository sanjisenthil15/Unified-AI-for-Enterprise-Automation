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
from core.security import verify_access_token
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

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that validates the JWT in the Authorization header
    and returns the corresponding active User ORM object.

    Raises HTTP 401 when:
      - The Authorization header is missing or malformed
      - The token signature is invalid or expired
      - The token payload is missing expected claims
      - No user with the encoded ID exists in the database

    Raises HTTP 403 when:
      - The user account is deactivated (is_active = False)

    Returns:
        The authenticated User ORM instance with role eagerly loaded.
    """
    # Dev bypass — treat every request as the seeded demo admin.
    if settings.AUTH_DISABLED:
        return _dev_user(db)

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    # Step 1: Decode and validate the JWT
    try:
        payload = verify_access_token(credentials.credentials)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    # Step 2: Load the user from the database, joining the role
    user: User | None = (
        db.query(User)
        .filter(User.id == user_id, User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise credentials_exception

    # Step 3: Ensure the account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact your administrator.",
        )

    return user


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
