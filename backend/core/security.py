"""
core/security.py

Security utilities for the authentication module.

Responsibilities:
  - Password hashing and verification using passlib (bcrypt)
  - JWT access token creation and verification using python-jose

All JWT parameters are read from config/settings.py.
No secrets are hard-coded in this file.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import settings


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
