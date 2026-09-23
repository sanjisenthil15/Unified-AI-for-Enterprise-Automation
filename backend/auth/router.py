"""
auth/router.py

FastAPI router for the Authentication module.

Endpoints:
    POST  /auth/register  — Create a new user account
    POST  /auth/login     — Authenticate and receive a JWT access token
    GET   /auth/me        — Return the currently authenticated user's profile

All business logic lives directly in this router because the auth
module is intentionally thin. If complexity grows, extract to
auth/service.py (already scaffolded).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.schemas import RoleResponse, Token, UserLogin, UserRegister, UserResponse
from config.database import get_db
from core.dependencies import get_current_user
from core.security import create_access_token, hash_password, verify_password
from models.role import Role
from models.user import User

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


# ------------------------------------------------------------------ #
# POST /auth/register
# ------------------------------------------------------------------ #

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Creates a new user account. The password is hashed with bcrypt "
        "before storage — the plain-text password is never persisted. "
        "The supplied role_id must reference an existing role."
    ),
)
def register(
    payload: UserRegister,
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Registration flow:
      1. Verify the requested role exists.
      2. Check that no account already uses the supplied email.
      3. Hash the password.
      4. Persist the new User row.
      5. Return the created user (without password).
    """

    # Step 1 — Validate role exists
    role: Role | None = db.query(Role).filter(Role.id == payload.role_id).first()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role with id={payload.role_id} does not exist.",
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
        role_id=payload.role_id,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)   # reload to populate server-side defaults (id, created_at)

    # Step 5 — Return safe response (Pydantic excludes hashed_password automatically)
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

    # Step 1 — Find user (soft-deleted accounts are treated as non-existent)
    user: User | None = (
        db.query(User)
        .filter(User.email == payload.email.lower(), User.deleted_at.is_(None))
        .first()
    )

    # Steps 2 — Verify password (also handles user-not-found case)
    if user is None or not verify_password(payload.password, user.hashed_password):
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

    # Step 4 — Build JWT payload and sign it
    token_data = {
        "sub": str(user.id),       # "sub" (subject) is the standard JWT claim for user ID
        "email": user.email,
        "role": user.role.name,    # embed role name for fast RBAC checks in dependencies
    }
    access_token = create_access_token(data=token_data)

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
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Returns the authenticated user's profile.

    Authentication is fully handled by the get_current_user dependency —
    this route only needs to return what the dependency resolved.

    The hashed_password field is excluded by UserResponse automatically.
    """
    return current_user


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
