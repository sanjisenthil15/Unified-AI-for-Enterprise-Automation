"""
scripts/rename_demo_employees.py

One-off: renames the 20 seeded demo employees — full_name AND email, both
derived from NEW_NAMES below (email slug drops single-letter "initial"
tokens, e.g. "Vishwa G" -> vishwa@employee.demo, not vishwa.g@...).
Project, job title, team lead status, role, and password all stay exactly
as seeded by seed_demo_org.py. Matched by creation order (User.id
ascending among @employee.demo accounts) — idempotent, safe to re-run.

NEW_NAMES has one duplicate ("srivatsan", positions 14 and 17) — the
second occurrence gets "2" appended to its email to avoid a collision,
since email must be unique.

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

EMAIL_DOMAIN = "employee.demo"


def title_case(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split())


def email_slug(name: str) -> str:
    """Lowercase, dot-separated, dropping single-letter "initial" tokens
    (e.g. the trailing "g" in "vishwa g")."""
    words = [w for w in name.lower().split() if len(w) > 1]
    return ".".join(words) if words else name.lower().split()[0]


def main() -> None:
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(User.email.like(f"%@{EMAIL_DOMAIN}"))
            .order_by(User.id.asc())
            .all()
        )
        if len(users) != len(NEW_NAMES):
            raise SystemExit(
                f"Expected {len(NEW_NAMES)} seeded demo users, found {len(users)}. "
                "Run seed_demo_org.py first, or check for extra/missing @employee.demo accounts."
            )

        seen_slugs: dict[str, int] = {}
        updates = []
        for user, new_name in zip(users, NEW_NAMES):
            slug = email_slug(new_name)
            seen_slugs[slug] = seen_slugs.get(slug, 0) + 1
            if seen_slugs[slug] > 1:
                slug = f"{slug}{seen_slugs[slug]}"  # disambiguate the duplicate "srivatsan"
            updates.append((user, title_case(new_name), f"{slug}@{EMAIL_DOMAIN}"))

        print(f"{'Old email':<40} {'New name':<20} {'New email'}")
        print("-" * 95)
        for user, new_full_name, new_email in updates:
            print(f"{user.email:<40} {new_full_name:<20} {new_email}")
            user.full_name = new_full_name
            user.email = new_email

        db.commit()
        print(f"\nUpdated {len(updates)} accounts.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
