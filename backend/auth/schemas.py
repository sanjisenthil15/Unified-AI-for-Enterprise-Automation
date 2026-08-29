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

from pydantic import BaseModel, EmailStr, Field, field_validator


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
        min_length=8,
        max_length=128,
        examples=["Str0ng!Pass"],
        description="Plain-text password (min 8 characters). Stored as bcrypt hash.",
    )
    role_id: int = Field(
        ...,
        ge=1,
        examples=[5],
        description="ID of the role to assign. Must exist in the roles table.",
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """
        Enforce a minimal password policy:
        - At least one uppercase letter
        - At least one digit
        Keeps security reasonable without over-engineering.
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


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


class TokenPayload(BaseModel):
    """
    Internal schema representing the decoded JWT claims.
    Used by the authentication dependency to extract user identity.
    """

    sub: str          # user ID as string
    role: str         # role name
    email: str
