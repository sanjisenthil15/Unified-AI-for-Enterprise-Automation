"""
core/security.py

Security utilities for the authentication module.

Responsibilities:
  - Password hashing and verification using passlib (bcrypt)
  - JWT access token creation and verification using python-jose

All JWT parameters are read from config/settings.py.
No secrets are hard-coded in this file.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import settings


# ------------------------------------------------------------------ #
# Password policy
# ------------------------------------------------------------------ #
PASSWORD_MIN_LENGTH = 8
# bcrypt only looks at the first 72 bytes and silently ignores the rest, so
# anything longer is rejected outright rather than quietly truncated.
PASSWORD_MAX_BYTES = 72


def validate_password_policy(password: str) -> str:
    """Single source of truth for user-chosen passwords (registration,
    password change). Raises ValueError with a user-facing message."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_BYTES} bytes.")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit.")
    return password


def generate_temporary_password() -> str:
    """Cryptographically secure one-time password for onboarding and
    administrative resets (~12 URL-safe chars, well under 72 bytes)."""
    return secrets.token_urlsafe(9)


# ------------------------------------------------------------------ #
# Password hashing context
# ------------------------------------------------------------------ #
# bcrypt is the recommended algorithm for password storage.
# deprecated="auto" automatically upgrades legacy hashes on next login.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Hash a plain-text password using bcrypt.

    Args:
        password: The raw password string provided by the user.

    Returns:
        A bcrypt hash string safe to store in the database.

    Example:
        hashed = hash_password("MyS3cretP@ss")
    """
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain-text password against a stored bcrypt hash.

    Args:
        plain_password:   The raw password submitted during login.
        hashed_password:  The bcrypt hash retrieved from the database.

    Returns:
        True if the password matches the hash, False otherwise.

    Example:
        is_valid = verify_password("MyS3cretP@ss", stored_hash)
    """
    return _pwd_context.verify(plain_password, hashed_password)


# ------------------------------------------------------------------ #
# JWT token utilities
# ------------------------------------------------------------------ #

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token.

    The token payload is a copy of `data` with an added `exp` (expiry)
    claim. The token is signed with SECRET_KEY using the ALGORITHM
    defined in settings.

    Args:
        data:           Arbitrary claims to encode, e.g. {"sub": str(user_id),
                        "role": "admin"}. Must be JSON-serialisable.
        expires_delta:  Optional custom lifetime. Defaults to
                        settings.ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        A signed JWT string ready to return to the client.

    Example:
        token = create_access_token({"sub": "42", "role": "hr"})
    """
    payload = data.copy()

    # Calculate expiry using UTC so the claim is timezone-aware
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload.update({"exp": expire})

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def create_user_access_token(user) -> str:
    """Issue a session token for `user`. The `ver` claim snapshots
    user.token_version; bumping that column in the database (password
    change, admin reset) invalidates every token issued before it — see
    core.dependencies._resolve_user."""
    return create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.name,
        "ver": user.token_version or 0,
    })


def verify_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Verifies the signature and the `exp` claim. Raises an exception if
    the token is invalid, expired, or tampered with — callers should
    catch this and return HTTP 401.

    Args:
        token: The raw JWT string extracted from the Authorization header.

    Returns:
        The decoded payload dictionary (e.g. {"sub": "42", "role": "hr",
        "exp": ...}).

    Raises:
        jose.JWTError: If the token signature is invalid, the token has
                       expired, or decoding fails for any reason.

    Example:
        try:
            payload = verify_access_token(token)
            user_id = int(payload["sub"])
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
    """
    # jwt.decode() automatically validates expiry ("exp" claim)
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    return payload
