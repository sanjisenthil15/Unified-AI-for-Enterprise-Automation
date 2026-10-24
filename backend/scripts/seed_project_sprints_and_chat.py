"""
scripts/seed_project_sprints_and_chat.py

One-off, idempotent: for each of the 3 seeded demo projects (Recruitment
AI / Meeting Intelligence / Customer Support Platform) — each already has
a team lead + 5 developers from seed_demo_org.py:

  - gives the 5 non-lead members distinct, realistic job titles instead
    of all sharing "Software Developer"
  - sets a deadline 3 months out, if not already set (this alone also
    auto-generates the project's weekly sprint shells, via the same
    code path create_project uses — see
    modules/employee_management/service.py:create_project)
  - assigns one task to every team member (lead included) in each of
    the first 4 weekly sprints, with mixed statuses, so the board and
    burndown chart have real content across more than just "this week"
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
WEEKS_TO_POPULATE = 4

# Lead always gets a coordination task; the 5 developers get these, in
# team order (matches the order seed_demo_org.py created them in).
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

# Same order as PROJECT_TASKS' 5 developers — a real team isn't five
# identical "Software Developer" rows.
PROJECT_JOB_TITLES = {
    "Recruitment AI": ["Frontend Developer", "Backend Developer", "QA Engineer", "DevOps Engineer", "UI/UX Designer"],
    "Meeting Intelligence": ["Backend Developer", "ML Engineer", "Frontend Developer", "QA Engineer", "DevOps Engineer"],
    "Customer Support Platform": ["Frontend Developer", "Backend Developer", "QA Engineer", "UI/UX Designer", "DevOps Engineer"],
}

# Status pattern for weeks 2+ (week 1 stays "todo" — freshly assigned),
# cycled across the 5 developers so the board isn't uniform.
WEEKLY_STATUS_CYCLE = ["in_progress", "done", "blocked", "todo", "in_progress"]


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

            titles = PROJECT_JOB_TITLES[project.name]
            retitled = 0
            for member, title in zip(others, titles):
                if member.job_title != title:
                    member.job_title = title
                    retitled += 1
            if retitled:
                db.commit()
                print(f"  gave {retitled} member(s) a distinct job title")
            else:
                print("  job titles already varied")

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

            sprints_in_order = sorted(sprints, key=lambda s: s.start_date)
            task_titles = PROJECT_TASKS[project.name]

            for week_index, sprint in enumerate(sprints_in_order[:WEEKS_TO_POPULATE], start=1):
                existing_tasks = db.query(SprintTask).filter(SprintTask.sprint_id == sprint.id).count()
                if existing_tasks > 0:
                    print(f"  '{sprint.name}' already has {existing_tasks} tasks")
                    continue

                assigned = 0
                if lead is not None:
                    db.add(SprintTask(
                        sprint_id=sprint.id, assignee_id=lead.id,
                        title=f"Week {week_index} planning & team coordination",
                        due_date=sprint.end_date,
                        status="done" if week_index < WEEKS_TO_POPULATE else "in_progress",
                        progress_percent=100 if week_index < WEEKS_TO_POPULATE else 50,
                    ))
                    assigned += 1

                for i, (member, base_title) in enumerate(zip(others, task_titles)):
                    title = base_title if week_index == 1 else f"{base_title} — week {week_index}"
                    task_status = "todo" if week_index == 1 else WEEKLY_STATUS_CYCLE[i]
                    progress = {"todo": 0, "in_progress": 50, "blocked": 25, "done": 100}[task_status]
                    db.add(SprintTask(
                        sprint_id=sprint.id, assignee_id=member.id,
                        title=title, due_date=sprint.end_date,
                        status=task_status, progress_percent=progress,
                    ))
                    assigned += 1

                db.commit()
                print(f"  assigned {assigned} tasks in '{sprint.name}' (due {sprint.end_date})")

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
