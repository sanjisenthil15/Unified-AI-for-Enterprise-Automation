"""
scripts/rename_demo_employees.py

One-off: renames the 20 seeded demo employees (full_name only — email,
project, job title, team lead status, role, password all stay exactly as
seeded by seed_demo_org.py). Matched by creation order (User.id ascending
among @employee.demo accounts), same order seed_demo_org.py created them in.

Run:
    cd backend && .venv\\Scripts\\python scripts\\rename_demo_employees.py
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.user import User  # noqa: E402

# In order — must match the 20 seeded accounts' creation order exactly.
NEW_NAMES = [
    "vidhya barathi",
    "tharun adith",
    "vishwa g",
    "sanjith",
    "thithiksha",
    "vishak",
    "vikas",
    "shyam",
    "srinithi",
    "sindhuja",
    "sasmitha",
    "varsha",
    "sundarabalan",
    "srivatsan",
    "sarathi",
    "vishnu",
    "srivatsan",
    "vishal raj",
    "yesvanth",
    "santhosh",
]


def title_case(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def main() -> None:
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(User.email.like("%@employee.demo"))
            .order_by(User.id.asc())
            .all()
        )
        if len(users) != len(NEW_NAMES):
            raise SystemExit(
                f"Expected {len(NEW_NAMES)} seeded demo users, found {len(users)}. "
                "Run seed_demo_org.py first, or check for extra/missing @employee.demo accounts."
            )

        print(f"{'Old name':<24} {'New name':<20} {'Email'}")
        print("-" * 80)
        for user, new_name in zip(users, NEW_NAMES):
            new_full_name = title_case(new_name)
            print(f"{user.full_name:<24} {new_full_name:<20} {user.email}")
            user.full_name = new_full_name

        db.commit()
        print(f"\nRenamed {len(users)} accounts.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
