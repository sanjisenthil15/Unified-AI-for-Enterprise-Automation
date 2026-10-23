"""
scripts/seed_demo_org.py

One-off seed script: creates 3 projects (named after this app's own
modules) and 20 employees — 1 Engineering Manager, 1 HR Manager, and 3
six-person project teams each with one Team Lead. Names come from the
class roster PDF supplied for this demo.

All seeded accounts share the password "Demo1234" (same convention as the
existing demo@demo.com account) so they're easy to log into for the demo —
this is seed data for a prototype, not a real onboarding flow, so a shared
known password is the practical choice here.

Idempotent: safe to re-run — looks up by email/name before creating.

Run:
    cd backend && .venv\\Scripts\\python scripts\\seed_demo_org.py
"""

import re
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from core.security import hash_password  # noqa: E402
from models.employee import Employee  # noqa: E402
from models.project import Project  # noqa: E402
from models.role import Role  # noqa: E402
from models.user import User  # noqa: E402

DEMO_PASSWORD = "Demo1234"

# In order from the supplied roster (namelist.pdf), register nos 714024104189-208.
NAMES = [
    "SANJAY B", "SANJAY R", "SANJAY S", "SANJITH S", "SANTHOSH P", "SARATHI R",
    "SARAVANA KRISHNAN M", "SASMITHA KRISHNAMOORTHY", "SATHISH KUMAR.S",
    "SHARVITHA G V", "SHIVA SURYA J", "SHIVANI V S", "SHREYAS.S",
    "SHRI RITHANYA.S", "SHRUTISRI S", "SHYAM G V", "SIDDARTH",
    "SIJU WILSON P", "SINDHUJA SANKARAMOORTHY", "SIVAPRASANTH B",
]

PROJECTS = [
    ("Recruitment AI", "AI-assisted resume screening and candidate ranking."),
    ("Meeting Intelligence", "Offline/online meeting transcription and AI summaries."),
    ("Customer Support Platform", "AI-assisted customer support ticketing and knowledge base."),
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")


def email_for(name: str) -> str:
    return f"{slugify(name)}@employee.demo"


def title_case(name: str) -> str:
    return " ".join(w.capitalize() for w in name.replace(".", " ").split())


def main() -> None:
    db = SessionLocal()
    try:
        employee_role = db.query(Role).filter(Role.name == "employee").first()
        hr_role = db.query(Role).filter(Role.name == "hr_manager").first()
        if employee_role is None or hr_role is None:
            raise SystemExit("Seeded roles are missing. Run `alembic upgrade head` first.")

        def get_or_create_employee(name: str, job_title: str, role: Role) -> Employee:
            email = email_for(name)
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(
                    full_name=title_case(name),
                    email=email,
                    hashed_password=hash_password(DEMO_PASSWORD),
                    role_id=role.id,
                    is_active=True,
                )
                db.add(user)
                db.flush()
            else:
                user.role_id = role.id  # keep role in sync on re-run

            employee = db.query(Employee).filter(Employee.user_id == user.id).first()
            if employee is None:
                employee = Employee(
                    user_id=user.id,
                    employee_code=f"EMP-{user.id:05d}",
                    job_title=job_title,
                    hire_date=date(2026, 1, 15),
                    employment_type="full_time",
                    status="active",
                )
                db.add(employee)
                db.flush()
            else:
                employee.job_title = job_title  # keep title in sync on re-run
            return employee

        def get_or_create_project(name: str, description: str) -> Project:
            project = db.query(Project).filter(Project.name == name).first()
            if project is None:
                project = Project(name=name, description=description)
                db.add(project)
                db.flush()
            return project

        names = iter(NAMES)
        created_summary = []

        manager = get_or_create_employee(next(names), "Engineering Manager", employee_role)
        created_summary.append((manager, "Engineering Manager (all projects)"))

        hr = get_or_create_employee(next(names), "HR Manager", hr_role)
        created_summary.append((hr, "HR Manager"))

        for proj_name, proj_desc in PROJECTS:
            project = get_or_create_project(proj_name, proj_desc)

            lead_name = next(names)
            lead = get_or_create_employee(lead_name, "Team Lead", employee_role)
            lead.project_id = project.id
            db.flush()
            project.team_lead_id = lead.id
            created_summary.append((lead, f"Team Lead — {proj_name}"))

            for _ in range(5):
                member_name = next(names)
                member = get_or_create_employee(member_name, "Software Developer", employee_role)
                member.project_id = project.id
                created_summary.append((member, f"Developer — {proj_name}"))

        db.commit()

        print(f"\nSeeded {len(created_summary)} employees. Shared password: {DEMO_PASSWORD}\n")
        print(f"{'Name':<24} {'Email':<36} {'Role'}")
        print("-" * 90)
        for employee, role_desc in created_summary:
            print(f"{employee.user.full_name:<24} {employee.user.email:<36} {role_desc}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
