"""
auth/schemas.py

Pydantic schemas for the Authentication module.

These schemas define and validate the shape of every request body
and response payload for the /auth endpoints.
They are completely separate from the ORM models — the ORM models
talk to the database; these schemas talk to the API boundary.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from core.security import validate_password_policy


# ------------------------------------------------------------------ #
# Request schemas
# ------------------------------------------------------------------ #

class UserRegister(BaseModel):
    """
    Payload for POST /auth/register.

    Constraints enforced here so they are validated before
    the database is ever touched.
    """

    full_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        examples=["Jane Doe"],
        description="User's display name (2–120 characters)",
    )
    email: EmailStr = Field(
        ...,
        examples=["jane.doe@company.com"],
        description="Unique email address used to log in",
    )
    password: str = Field(
        ...,
        examples=["Str0ng!Pass"],
        description=(
            "Plain-text password: 8+ characters, at most 72 bytes, with an "
            "uppercase letter and a digit. Stored as a bcrypt hash."
        ),
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_policy(v)


class UserLogin(BaseModel):
    """
    Payload for POST /auth/login.
    """

    email: EmailStr = Field(
        ...,
        examples=["jane.doe@company.com"],
    )
    password: str = Field(
        ...,
        min_length=1,
        examples=["Str0ng!Pass"],
        description="Plain-text password to verify against stored hash",
    )


class ChangePasswordRequest(BaseModel):
    """Payload for POST /auth/change-password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(
        ...,
        description="8+ characters, at most 72 bytes, with an uppercase letter and a digit.",
    )
    confirm_password: str = Field(..., min_length=1)

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        return validate_password_policy(v)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirmation do not match.")
        return self


# ------------------------------------------------------------------ #
# Response schemas
# ------------------------------------------------------------------ #

class RoleResponse(BaseModel):
    """Embedded role information returned inside UserResponse."""

    id: int
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """
    Safe user representation returned by /auth/register and /auth/me.
    The hashed_password field is intentionally excluded.
    """

    id: int
    full_name: str
    email: str
    is_active: bool
    must_change_password: bool = False
    role: RoleResponse
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """
    JWT token payload returned by POST /auth/login.
    Follows OAuth2 Bearer token conventions.
    """

    access_token: str = Field(
        ...,
        description="Signed JWT access token to include in subsequent requests",
    )
    token_type: str = Field(
        default="bearer",
        description="Always 'bearer' — used in the Authorization header",
    )


class AdminPasswordResetResponse(BaseModel):
    """Returned ONCE to the admin/HR who performed the reset. The temporary
    password is never stored in plain text or returned by any other API."""

    user_id: int
    temporary_password: str
    must_change_password: bool = True


class TokenPayload(BaseModel):
    """
    Internal schema representing the decoded JWT claims.
    Used by the authentication dependency to extract user identity.
    """

    sub: str          # user ID as string
    role: str         # role name
    email: str
