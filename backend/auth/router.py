"""
auth/router.py

FastAPI router for the Authentication module.

Endpoints:
    POST  /auth/register                    — Create a new user account
    POST  /auth/login                       — Authenticate and receive a JWT access token
    GET   /auth/me                          — Return the currently authenticated user's profile
    POST  /auth/change-password             — Change own password (also completes first login)
    POST  /auth/users/{user_id}/reset-password — Admin/HR issues a new temporary password

All business logic lives directly in this router because the auth
module is intentionally thin. If complexity grows, extract to
auth/service.py (already scaffolded).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.schemas import (
    AdminPasswordResetResponse,
    ChangePasswordRequest,
    CustomerRegister,
    RoleResponse,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
)
from config.database import get_db
from config.settings import settings
from core import audit, rate_limit
from core.dependencies import get_current_user, get_current_user_allow_password_change, require_roles
from core.permissions import PASSWORD_RESET_REQUESTER_ROLES, PASSWORD_RESET_TARGETS
from core.security import (
    create_user_access_token,
    generate_temporary_password,
    hash_password,
    verify_password,
)
from models.role import Role
from models.user import User

logger = logging.getLogger(__name__)

# All routes in this router are prefixed with /auth
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ------------------------------------------------------------------ #
# GET /auth/roles
# ------------------------------------------------------------------ #

@router.get(
    "/roles",
    response_model=list[RoleResponse],
    summary="List available roles",
    description="Public listing of roles, used to populate the registration form.",
)
def list_roles(db: Session = Depends(get_db)) -> list[Role]:
    return db.query(Role).order_by(Role.id).all()


@router.get(
    "/registration-status",
    summary="Whether public self-registration is open",
    description="Lets the login screen hide the sign-up link when accounts are provisioned by HR / Admin only.",
)
def registration_status() -> dict:
    return {
        "enabled": settings.public_registration_enabled,
        "customer_registration_enabled": settings.customer_registration_enabled,
    }


# ------------------------------------------------------------------ #
# POST /auth/register
# ------------------------------------------------------------------ #

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Creates a new user account with the default 'employee' role. "
        "The password is hashed with bcrypt before storage — the "
        "plain-text password is never persisted. Higher-privilege roles "
        "are assigned by HR/admin via Employee Management, not self-serve."
    ),
)
def register(
    payload: UserRegister,
    request: Request,
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Registration flow:
      1. Resolve the default 'employee' role (self-serve accounts never
         choose their own role — that would let anyone grant themselves
         admin).
      2. Check that no account already uses the supplied email.
      3. Hash the password.
      4. Persist the new User row.
      5. Return the created user (without password).
    """

    # Step 0 — Public sign-up is off on hosted deployments unless explicitly
    # enabled (ALLOW_PUBLIC_REGISTRATION); there, Admin / HR provision
    # accounts through Employee Management. Also throttled per client IP.
    if not settings.public_registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled. Ask HR or an administrator to create your account.",
        )
    ip = rate_limit.client_ip(request)
    rate_limit.check_registration_allowed(db, ip)

    # Step 1 — Always the default role; never trust a client-supplied role_id here
    role: Role | None = db.query(Role).filter(Role.name == "employee").first()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default 'employee' role is missing. Run `alembic upgrade head`.",
        )

    # Step 2 — Check email uniqueness
    existing: User | None = (
        db.query(User)
        .filter(User.email == payload.email.lower(), User.deleted_at.is_(None))
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Step 3 — Hash password (plain text never stored)
    hashed = hash_password(payload.password)

    # Step 4 — Create and persist user
    new_user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),   # normalise to lowercase for consistency
        hashed_password=hashed,
        role_id=role.id,
        is_active=True,
    )
    db.add(new_user)
    rate_limit.record_registration(db, ip)
    db.commit()
    db.refresh(new_user)   # reload to populate server-side defaults (id, created_at)

    # Step 5 — Return safe response (Pydantic excludes hashed_password automatically)
    return new_user


# ------------------------------------------------------------------ #
# POST /auth/register-customer
# ------------------------------------------------------------------ #

@router.post(
    "/register-customer",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an external customer account",
    description=(
        "Creates a customer account with the 'customer' role strictly assigned by the backend. "
        "Allows external clients to self-register and track customer support tickets."
    ),
)
def register_customer(
    payload: CustomerRegister,
    request: Request,
    db: Session = Depends(get_db),
) -> UserResponse:
    if not settings.customer_registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer self-registration is currently disabled.",
        )
    ip = rate_limit.client_ip(request)
    rate_limit.check_registration_allowed(db, ip)

    # Step 1 — Resolve customer role
    role: Role | None = db.query(Role).filter(Role.name == "customer").first()
    if role is None:
        role = Role(
            name="customer",
            description="External customer account for support ticket submission and tracking",
        )
        db.add(role)
        db.commit()
        db.refresh(role)

    # Step 2 — Check email uniqueness
    existing: User | None = (
        db.query(User)
        .filter(User.email == payload.email.lower(), User.deleted_at.is_(None))
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Step 3 — Hash password
    hashed = hash_password(payload.password)

    # Step 4 — Create and persist customer user
    new_user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hashed,
        role_id=role.id,
        is_active=True,
    )
    db.add(new_user)
    rate_limit.record_registration(db, ip)
    db.commit()
    db.refresh(new_user)

    return new_user


# ------------------------------------------------------------------ #
# POST /auth/login
# ------------------------------------------------------------------ #

@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive a JWT access token",
    description=(
        "Verifies the supplied credentials and returns a signed JWT "
        "access token. Include this token in subsequent requests as: "
        "Authorization: Bearer <token>"
    ),
)
def login(
    payload: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
) -> Token:
    """
    Login flow:
      1. Look up the user by email.
      2. Verify the plain-text password against the stored bcrypt hash.
      3. Confirm the account is active.
      4. Issue a signed JWT containing user id, email, and role name.
      5. Return the token.

    Intentionally returns the same generic error for both "user not found"
    and "wrong password" to prevent user enumeration attacks.
    """

    # Step 0 — Refuse while this account / IP is over its failure budget
    # (before any password check, so the limit can't be used as an oracle).
    ip = rate_limit.client_ip(request)
    rate_limit.check_login_allowed(db, payload.email, ip)

    # Step 1 — Find user (soft-deleted accounts are treated as non-existent)
    user: User | None = (
        db.query(User)
        .filter(User.email == payload.email.lower(), User.deleted_at.is_(None))
        .first()
    )

    # Steps 2 — Verify password (also handles user-not-found case)
    if user is None or not verify_password(payload.password, user.hashed_password):
        # Audited without the attempted email or password — only the
        # account id when the email belongs to a real account.
        audit.record_event(db, "auth.login_failed", "user", user.id if user else None)
        rate_limit.record_login_failure(db, payload.email, ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3 — Confirm account is enabled
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact your administrator.",
        )

    # Step 4 — Sign a JWT stamped with the user's current session version.
    # Accounts that still use a temporary password can log in, but every
    # application API will answer 403 password_change_required until they
    # call /auth/change-password (see core.dependencies.get_current_user).
    access_token = create_user_access_token(user)
    audit.record_event(db, "auth.login_succeeded", "user", user.id, actor=user)
    rate_limit.clear_login_failures(db, payload.email, ip)
    db.commit()

    # Step 5 — Return bearer token
    return Token(access_token=access_token, token_type="bearer")


# ------------------------------------------------------------------ #
# GET /auth/me
# ------------------------------------------------------------------ #

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the currently authenticated user",
    description=(
        "Returns the profile of the user identified by the JWT in the "
        "Authorization header. Requires a valid, non-expired token."
    ),
)
def get_me(
    current_user: User = Depends(get_current_user_allow_password_change),
) -> UserResponse:
    """
    Returns the authenticated user's profile.

    Reachable even while must_change_password is set, so the frontend can
    see that flag and route the user to the mandatory Change Password screen.

    The hashed_password field is excluded by UserResponse automatically.
    """
    return current_user


# ------------------------------------------------------------------ #
# POST /auth/change-password
# ------------------------------------------------------------------ #

@router.post(
    "/change-password",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Change your own password",
    description=(
        "Verifies the current password, applies the password policy, then "
        "revokes every existing session for this account and returns a "
        "fresh token. Also completes the mandatory first-login change."
    ),
)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_allow_password_change),
) -> Token:
    # 400 (not 401) for a wrong current password: the caller IS authenticated,
    # and a 401 would make the frontend treat it as an expired session.
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if verify_password(payload.new_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different from your current password.")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.must_change_password = False
    current_user.token_version = (current_user.token_version or 0) + 1
    current_user.password_changed_at = datetime.now(timezone.utc)
    audit.label(db, current_user, "user.password_changed")
    db.commit()
    db.refresh(current_user)

    logger.info("Password changed for user_id=%s", current_user.id)
    return Token(access_token=create_user_access_token(current_user), token_type="bearer")


# ------------------------------------------------------------------ #
# POST /auth/users/{user_id}/reset-password
# ------------------------------------------------------------------ #

@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminPasswordResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue a new temporary password for another account (admin / HR)",
    description=(
        "Generates a one-time temporary password, forces a change at the "
        "target's next login and revokes all of their existing sessions. "
        "The temporary password is shown only in this response."
    ),
)
def admin_reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(PASSWORD_RESET_REQUESTER_ROLES)),
) -> AdminPasswordResetResponse:
    if user_id == current_user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot reset your own password here. Use Change Password instead.",
        )

    target: User | None = (
        db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User id={user_id} not found.")

    allowed_targets = PASSWORD_RESET_TARGETS.get(current_user.role.name, set())
    if target.role.name not in allowed_targets:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"A {current_user.role.name} cannot reset the password of a {target.role.name} account.",
        )

    temp_password = generate_temporary_password()
    target.hashed_password = hash_password(temp_password)
    target.must_change_password = True
    target.token_version = (target.token_version or 0) + 1
    target.password_reset_by_id = current_user.id
    target.password_reset_at = datetime.now(timezone.utc)
    audit.label(db, target, "user.password_reset")
    db.commit()

    # Identifiers only — the password itself is never logged.
    logger.info("Administrative password reset: actor_user_id=%s target_user_id=%s", current_user.id, target.id)
    return AdminPasswordResetResponse(user_id=target.id, temporary_password=temp_password)


# ------------------------------------------------------------------ #
# GET /auth/users
# ------------------------------------------------------------------ #

@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="List active users",
    description="Any authenticated user may list active accounts, e.g. to assign a meeting action item.",
)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    return (
        db.query(User)
        .filter(User.is_active.is_(True), User.deleted_at.is_(None))
        .order_by(User.full_name)
        .all()
    )
