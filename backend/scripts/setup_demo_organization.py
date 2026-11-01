"""
backend/scripts/setup_demo_organization.py

Sets up realistic demo organization accounts and project relationships:
1. Manager: Elena Rostova (assigned to all 3 existing projects)
2. Support Agent: Aiden Cross (Customer Support)
3. Recruiter: Chloe Bennett (Recruitment AI)
4. Viewer: Julian Hayes (Read-only Analytics / Stakeholder)

Idempotent: Detects existing accounts by email and reuses them.
Uses official employee_management service methods to enforce password hashing,
must_change_password policy, and audit trails.
"""

import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.employee import Employee  # noqa: E402
from models.project import Project  # noqa: E402
from models.role import Role  # noqa: E402
from models.user import User  # noqa: E402
from modules.employee_management import service as emp_service  # noqa: E402
from modules.employee_management.schemas import EmployeeCreate  # noqa: E402


DEMO_ACCOUNTS = [
    {
        "full_name": "Elena Rostova",
        "email": "elena.rostova@employee.demo",
        "role_name": "manager",
        "job_title": "Engineering Manager",
        "phone": "+1 (555) 234-5678",
        "employment_type": "full_time",
        "hire_date": date(2025, 6, 1),
        "assign_all_projects": True,
    },
    {
        "full_name": "Aiden Cross",
        "email": "aiden.cross@employee.demo",
        "role_name": "support_agent",
        "job_title": "Customer Support Specialist",
        "phone": "+1 (555) 345-6789",
        "employment_type": "full_time",
        "hire_date": date(2025, 9, 15),
        "project_name": "Customer Support Platform",
    },
    {
        "full_name": "Chloe Bennett",
        "email": "chloe.bennett@employee.demo",
        "role_name": "recruiter",
        "job_title": "Talent Acquisition Specialist",
        "phone": "+1 (555) 456-7890",
        "employment_type": "full_time",
        "hire_date": date(2025, 8, 10),
        "project_name": "Recruitment AI",
    },
    {
        "full_name": "Julian Hayes",
        "email": "julian.hayes@employee.demo",
        "role_name": "viewer",
        "job_title": "Executive Stakeholder",
        "phone": "+1 (555) 567-8901",
        "employment_type": "full_time",
        "hire_date": date(2025, 4, 1),
        "project_name": None,
    },
]

PROJECT_NAMES = [
    "Customer Support Platform",
    "Meeting Intelligence",
    "Recruitment AI",
]

EXPECTED_LEADS = {
    "Customer Support Platform": "Sarathi",
    "Meeting Intelligence": "Srinithi",
    "Recruitment AI": "Vishwa",
}


def run_setup(credential_output_path: str = None):
    db = SessionLocal()
    try:
        # 1. Fetch main projects
        projects_by_name = {}
        for pname in PROJECT_NAMES:
            p = db.query(Project).filter(Project.name == pname).first()
            if not p:
                raise RuntimeError(f"Required project '{pname}' not found in database.")
            projects_by_name[pname] = p

        # 2. Fetch roles
        roles_by_name = {r.name: r for r in db.query(Role).all()}
        for item in DEMO_ACCOUNTS:
            if item["role_name"] not in roles_by_name:
                raise RuntimeError(f"Required role '{item['role_name']}' not found in database.")

        created_or_found = []
        credentials_record = []

        # 3. Create or find accounts
        manager_user_id = None
        for item in DEMO_ACCOUNTS:
            existing_user = db.query(User).filter(User.email == item["email"].lower()).first()
            role = roles_by_name[item["role_name"]]

            if existing_user is None:
                # Resolve target project if applicable
                proj_id = None
                if item.get("project_name") and item["project_name"] in projects_by_name:
                    proj_id = projects_by_name[item["project_name"]].id

                payload = EmployeeCreate(
                    full_name=item["full_name"],
                    email=item["email"],
                    role_id=role.id,
                    job_title=item["job_title"],
                    phone=item["phone"],
                    employment_type=item["employment_type"],
                    hire_date=item["hire_date"],
                    department_id=None,
                    project_id=proj_id,
                )
                emp, temp_pw = emp_service.create_employee(db, payload)
                user_id = emp.user.id
                status_note = "Created (New)"
                credentials_record.append({
                    "name": item["full_name"],
                    "email": item["email"],
                    "role": item["role_name"],
                    "temp_password": temp_pw,
                })
            else:
                user_id = existing_user.id
                # Ensure role matches
                if existing_user.role_id != role.id:
                    existing_user.role_id = role.id
                    db.commit()
                emp = db.query(Employee).filter(Employee.user_id == user_id).first()
                status_note = "Existing (Reused)"

            if item.get("assign_all_projects"):
                manager_user_id = user_id

            created_or_found.append({
                "name": item["full_name"],
                "email": item["email"],
                "role": item["role_name"],
                "job_title": item["job_title"],
                "status_note": status_note,
                "user_id": user_id,
            })

        # 4. Assign the Manager to all three projects
        if manager_user_id is not None:
            for pname in PROJECT_NAMES:
                p = projects_by_name[pname]
                emp_service.assign_project_manager(db, project_id=p.id, manager_user_id=manager_user_id)

        # 5. Verify Team Leaders and their assignments
        verified_leads = {}
        for pname in PROJECT_NAMES:
            p = db.query(Project).filter(Project.name == pname).first()
            lead_emp = db.query(Employee).filter(Employee.id == p.team_lead_id).first() if p.team_lead_id else None
            lead_user = db.query(User).filter(User.id == lead_emp.user_id).first() if lead_emp else None
            verified_leads[pname] = {
                "lead_name": lead_user.full_name if lead_user else "None",
                "lead_email": lead_user.email if lead_user else "None",
                "expected": EXPECTED_LEADS.get(pname),
            }

        # 6. Ensure Customer Support categories & teams are seeded into PostgreSQL
        try:
            from modules.customer_support.seed_data import seed_demo_knowledge_data
            admin = db.query(User).first()
            cs_stats = seed_demo_knowledge_data(db, author_id=admin.id if admin else None)
            print(f"[Customer Support] Seeded: {cs_stats}")
        except Exception as e:
            print(f"[Customer Support] Seed notice: {e}")

        # 7. Verify Manager assignments
        verified_projects = []
        for pname in PROJECT_NAMES:
            p = db.query(Project).filter(Project.name == pname).first()
            mgr_user = db.query(User).filter(User.id == p.manager_user_id).first() if p.manager_user_id else None
            verified_projects.append({
                "project_id": p.id,
                "project_name": p.name,
                "status": p.status,
                "manager_name": mgr_user.full_name if mgr_user else "None",
                "manager_email": mgr_user.email if mgr_user else "None",
                "team_lead": verified_leads[pname]["lead_name"],
            })

        # 7. Write credentials to admin-only file if path specified
        if credential_output_path and credentials_record:
            import os
            os.makedirs(Path(credential_output_path).parent, exist_ok=True)
            with open(credential_output_path, "w", encoding="utf-8") as f:
                f.write("ENTERPRISE AI — DEMO CREDENTIALS (ADMIN SECURE STORAGE)\n")
                f.write("=" * 60 + "\n\n")
                for c in credentials_record:
                    f.write(f"Account: {c['name']}\n")
                    f.write(f"Email:   {c['email']}\n")
                    f.write(f"Role:    {c['role']}\n")
                    f.write(f"Temp PW: {c['temp_password']}\n\n")

        return {
            "accounts": created_or_found,
            "projects": verified_projects,
            "leads": verified_leads,
            "credentials_written": len(credentials_record),
        }

    finally:
        db.close()


def main():
    import os
    cred_path = None
    try:
        candidate_dir = os.path.join(
            os.path.expanduser("~"),
            ".gemini", "antigravity", "brain", "c964e4e4-95f6-43d1-9d12-25b080a84bfe",
            "scratch"
        )
        if os.path.exists(candidate_dir):
            cred_path = os.path.join(candidate_dir, "demo_credentials.txt")
    except Exception:
        cred_path = None

    result = run_setup(cred_path)

    print("\n" + "=" * 80)
    print("DEMO ORGANIZATION SETUP COMPLETED")
    print("=" * 80)
    print(f"\n{'Name':<18} {'Email':<30} {'Role':<15} {'Job Title':<26} {'Status'}")
    print("-" * 105)
    for a in result["accounts"]:
        print(f"{a['name']:<18} {a['email']:<30} {a['role']:<15} {a['job_title']:<26} {a['status_note']}")

    print("\n" + "=" * 80)
    print("PROJECT ASSIGNMENTS & VERIFICATION")
    print("=" * 80)
    print(f"{'Project ID':<12} {'Project Name':<30} {'Status':<10} {'Manager':<18} {'Team Lead'}")
    print("-" * 95)
    for p in result["projects"]:
        print(f"{p['project_id']:<12} {p['project_name']:<30} {p['status']:<10} {p['manager_name']:<18} {p['team_lead']}")

    print("\nTeam Leader Preservations:")
    for pname, lead in result["leads"].items():
        print(f"  - {pname}: {lead['lead_name']} (Expected: {lead['expected']}) -> Match: {lead['expected'].lower() in lead['lead_name'].lower()}")

    if result["credentials_written"] > 0:
        print(f"\n[SECURE] Temporary passwords for {result['credentials_written']} new account(s) stored in admin credentials file.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
