"""
scripts/rotate_admin_password.py

Rotates the admin account password (default: demo@demo.com).
Enforces enterprise password policy, updates hashed_password, increments
token_version (invalidating active JWT sessions), sets password_changed_at,
and clears must_change_password.

Prints nothing secret to standard output or logs.

Usage:
    cd backend && .venv/Scripts/python -m scripts.rotate_admin_password [--email <email>] [--password <password>]
"""

import argparse
import getpass
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402, F401 - register all ORM models
from config.database import SessionLocal  # noqa: E402
from core.security import hash_password, validate_password_policy  # noqa: E402
from models.user import User  # noqa: E402

logger = logging.getLogger("rotate_admin_password")


def rotate_admin_password(
    email: str = "demo@demo.com",
    new_password: str | None = None,
) -> bool:
    """Rotates admin password safely. Returns True on success, False on failure."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return False

        if not new_password:
            try:
                pw1 = getpass.getpass(f"Enter new password for {email}: ")
                pw2 = getpass.getpass("Confirm new password: ")
            except (KeyboardInterrupt, EOFError):
                print("\nPassword rotation cancelled.")
                return False

            if pw1 != pw2:
                print("Error: Passwords do not match.")
                return False
            new_password = pw1

        try:
            validate_password_policy(new_password)
        except Exception as exc:
            print(f"Error: Password policy violation - {exc}")
            return False

        user.hashed_password = hash_password(new_password)
        user.token_version = (user.token_version or 1) + 1
        user.password_changed_at = datetime.now(timezone.utc)
        user.must_change_password = False

        db.commit()
        print(f"Admin password rotated successfully for {email}.")
        return True
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to rotate admin password")
        print("Error: An internal database error occurred while rotating the password.")
        return False
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate enterprise admin password safely.")
    parser.add_argument(
        "--email",
        default="demo@demo.com",
        help="Email of the account to rotate (default: demo@demo.com)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="New password (if omitted, will securely prompt with getpass)",
    )
    args = parser.parse_args()

    success = rotate_admin_password(email=args.email, new_password=args.password)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

