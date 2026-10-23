"""
scripts/seed_project_sprints_and_chat.py

One-off, idempotent: for each of the 3 seeded demo projects (Recruitment
AI / Meeting Intelligence / Customer Support Platform) — each already has
a team lead + 5 developers from seed_demo_org.py, but no deadline, no
sprints, and no chat group:

  - sets a deadline 3 months out, if not already set (this alone also
    auto-generates the project's weekly sprint shells, via the same
    code path create_project uses — see
    modules/employee_management/service.py:create_project)
  - assigns one task to every team member (lead included) in the first
    sprint, so the board isn't empty
  - creates a group chat for the team ("<Project> Team"), with a
    "general" channel and every member added

Run:
    cd backend && .venv\\Scripts\\python scripts\\seed_project_sprints_and_chat.py
"""

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.chat_group import ChatGroup  # noqa: E402
from models.employee import Employee  # noqa: E402
from models.project import Project  # noqa: E402
from models.sprint import Sprint  # noqa: E402
from models.sprint_task import SprintTask  # noqa: E402
from modules.chat.service import create_group  # noqa: E402
from modules.sprints.service import _generate_weekly_sprints_for_project  # noqa: E402

DEADLINE_MONTHS_OUT = 3

# Lead always gets a coordination task; the 5 developers get these,
# in team order.
PROJECT_TASKS = {
    "Recruitment AI": [
        "Resume parsing module",
        "Candidate ranking algorithm",
        "Interview scheduler integration",
        "Resume upload UI",
        "Fit-score dashboard",
    ],
    "Meeting Intelligence": [
        "Transcription pipeline",
        "Speaker diarization",
        "Meeting summary generation",
        "Action item extraction",
        "Audio upload UI",
    ],
    "Customer Support Platform": [
        "Ticket triage system",
        "Live chat widget",
        "Escalation detection",
        "Knowledge base search",
        "Agent dashboard",
    ],
}


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, 28)  # keep it simple, no month-length edge cases
    return date(year, month, day)


def main() -> None:
    db = SessionLocal()
    try:
        projects = db.query(Project).filter(Project.name.in_(PROJECT_TASKS.keys())).all()
        if len(projects) != 3:
            raise SystemExit(
                f"Expected 3 seeded projects (Recruitment AI / Meeting Intelligence / "
                f"Customer Support Platform), found {len(projects)}. Run seed_demo_org.py first."
            )

        for project in projects:
            print(f"\n=== {project.name} ===")
            members = (
                db.query(Employee)
                .filter(Employee.project_id == project.id, Employee.deleted_at.is_(None))
                .order_by(Employee.id)
                .all()
            )
            lead = next((m for m in members if m.id == project.team_lead_id), None)
            others = [m for m in members if m.id != project.team_lead_id]

            if project.deadline is None:
                project.deadline = _add_months(date.today(), DEADLINE_MONTHS_OUT)
                db.commit()
                print(f"  deadline -> {project.deadline}")
            else:
                print(f"  deadline already set -> {project.deadline}")

            existing_sprints = db.query(Sprint).filter(Sprint.project_id == project.id).order_by(Sprint.start_date).all()
            if not existing_sprints:
                sprints = _generate_weekly_sprints_for_project(db, project, lead)
                print(f"  generated {len(sprints)} weekly sprints")
            else:
                sprints = existing_sprints
                print(f"  {len(sprints)} sprints already exist")

            first_sprint = min(sprints, key=lambda s: s.start_date)
            existing_tasks = db.query(SprintTask).filter(SprintTask.sprint_id == first_sprint.id).count()
            if existing_tasks == 0:
                titles = PROJECT_TASKS[project.name]
                assigned = 0
                if lead is not None:
                    db.add(SprintTask(
                        sprint_id=first_sprint.id, assignee_id=lead.id,
                        title="Sprint planning & team coordination",
                        due_date=first_sprint.end_date, status="todo", progress_percent=0,
                    ))
                    assigned += 1
                for member, title in zip(others, titles):
                    db.add(SprintTask(
                        sprint_id=first_sprint.id, assignee_id=member.id,
                        title=title, due_date=first_sprint.end_date, status="todo", progress_percent=0,
                    ))
                    assigned += 1
                db.commit()
                print(f"  assigned {assigned} weekly tasks in '{first_sprint.name}' (due {first_sprint.end_date})")
            else:
                print(f"  '{first_sprint.name}' already has {existing_tasks} tasks")

            existing_group = db.query(ChatGroup).filter(ChatGroup.project_id == project.id).first()
            if existing_group is None and lead is not None:
                payload = SimpleNamespace(
                    project_id=project.id,
                    name=f"{project.name} Team",
                    member_user_ids=[m.user_id for m in members],
                )
                create_group(db, lead.user, lead, payload)
                print(f"  created chat group '{project.name} Team' with {len(members)} members")
            elif existing_group is not None:
                print("  chat group already exists")
            else:
                print("  no team lead assigned — skipping chat group")

        print("\nDone.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
