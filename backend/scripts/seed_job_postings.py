"""
scripts/seed_job_postings.py

One-off, idempotent: seeds several pre-built job postings into HR
Recruitment so there's real content to pick from (resume analysis
filters/matches against a *selected* job posting, which needs more than
one to be meaningful). Reuses the same role presets as
frontend/src/data/jobRoleTemplates.js, created by the seeded HR manager.

Run:
    cd backend && .venv\\Scripts\\python scripts\\seed_job_postings.py
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.job_posting import JobPosting  # noqa: E402
from models.user import User  # noqa: E402

HR_EMAIL = "tharun.adith@employee.demo"

# Mirrors frontend/src/data/jobRoleTemplates.js — kept as a separate,
# backend-side list rather than imported, since the frontend file is JS
# and this is a one-off Python script, not a shared module.
JOB_POSTINGS = [
    {
        "title": "Software Engineer",
        "required_skills": "JavaScript, React, Node.js, REST APIs, Git",
        "description": "Design, build, and maintain features across our web application stack, working closely with product and design.",
        "experience_level": "mid",
        "min_education": "Bachelor's Degree",
    },
    {
        "title": "Senior Backend Engineer",
        "required_skills": "Python, FastAPI, PostgreSQL, Docker, System Design",
        "description": "Own backend services end to end — API design, data modeling, performance, and reliability — and mentor junior engineers.",
        "experience_level": "senior",
        "min_education": "Bachelor's Degree",
    },
    {
        "title": "Product Manager",
        "required_skills": "Roadmapping, User Research, Analytics, Stakeholder Communication",
        "description": "Define product strategy and roadmap, gather requirements from stakeholders, and work with engineering/design to ship features.",
        "experience_level": "mid",
        "min_education": "Bachelor's Degree",
    },
    {
        "title": "Data Analyst",
        "required_skills": "SQL, Python, Excel, Data Visualization, Statistics",
        "description": "Analyze business data to surface insights, build dashboards, and support data-driven decision making across teams.",
        "experience_level": "junior",
        "min_education": "Bachelor's Degree",
    },
    {
        "title": "DevOps Engineer",
        "required_skills": "AWS/Azure, Docker, Kubernetes, CI/CD, Terraform",
        "description": "Build and maintain deployment pipelines and cloud infrastructure, improving reliability, scalability, and developer velocity.",
        "experience_level": "mid",
        "min_education": "Bachelor's Degree",
    },
    {
        "title": "QA Engineer",
        "required_skills": "Test Automation, Selenium/Playwright, API Testing, Bug Tracking",
        "description": "Design and execute manual and automated test plans to ensure product quality before release.",
        "experience_level": "entry",
        "min_education": "Bachelor's Degree",
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        hr_user = db.query(User).filter(User.email == HR_EMAIL).first()
        if hr_user is None:
            raise SystemExit(f"Seeded HR manager account {HR_EMAIL!r} not found. Run seed_demo_org.py first.")

        existing_titles = {
            j.title for j in db.query(JobPosting).filter(JobPosting.created_by == hr_user.id).all()
        }

        created = 0
        for posting in JOB_POSTINGS:
            if posting["title"] in existing_titles:
                print(f"  already exists: {posting['title']}")
                continue
            db.add(JobPosting(
                title=posting["title"],
                description=posting["description"],
                required_skills=posting["required_skills"],
                min_education=posting["min_education"],
                experience_level=posting["experience_level"],
                created_by=hr_user.id,
                status="active",
            ))
            created += 1
            print(f"  created: {posting['title']}")

        db.commit()
        print(f"\nDone — {created} new job posting(s) created.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
