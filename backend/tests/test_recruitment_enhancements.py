"""Tests for HR Recruitment Top-N Ranking + Interview Invitation Email (Feature 2).

Verifies:
1. Top-N candidate ranking order (descending scores, rank 1..N).
2. Criteria differentiation (meets_criteria for score >= 50 and positive recommendation vs error/low score).
3. Graceful handling of fewer candidates than requested N.
4. Validation of top_n query param (rejects < 1).
5. RBAC enforcement: only authorized HR/Admin roles can access top candidates or send invites.
6. Interview invitation sending, application status update, and audit log generation.
7. Simulated fallback when SMTP is unconfigured.
"""
import json
import uuid
from datetime import datetime, timezone

from models.audit_log import AuditLog
from models.job_posting import JobPosting
from models.resume import Resume
from models.candidate import Candidate


BASE = "/api/v1/recruitment"


def test_top_n_candidate_ranking(client, db, new_user):
    tag = uuid.uuid4().hex[:8]
    hr_user = new_user("Recruiter HR", role="hr_manager")
    plain_user = new_user("Plain User", role="employee")

    # 1. Create a JobPosting
    job = JobPosting(
        title=f"Lead Cloud Architect {tag}",
        description="Design scalable cloud platforms",
        required_skills="AWS, Kubernetes, Terraform, Python",
        min_education="Bachelor's Degree",
        experience_level="senior",
        status="active",
        created_by=hr_user["id"],
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 2. Create several resumes with different scores and statuses
    r1 = Resume(
        job_posting_id=job.id,
        candidate_name="Alice Architect",
        candidate_email="alice@cloud.example",
        file_name="alice_cv.pdf",
        file_path="obj:recruitment-resumes/alice.pdf",
        extracted_text="Expert in AWS, Kubernetes, Terraform, Python with 8 years experience.",
        ai_score=94.5,
        recommendation="selected",
        status="analysed",
        strengths="AWS, Kubernetes, Architecture",
        missing_skills="None",
        ai_summary=json.dumps({
            "matched_skills": "AWS, Kubernetes, Terraform",
            "missing_skills": "None",
            "match_score": 94.5,
            "recommendation_label": "Strong Match",
        }),
    )
    r2 = Resume(
        job_posting_id=job.id,
        candidate_name="Bob Builder",
        candidate_email="bob@cloud.example",
        file_name="bob_cv.pdf",
        file_path="obj:recruitment-resumes/bob.pdf",
        extracted_text="DevOps engineer skilled in Terraform and Docker.",
        ai_score=82.0,
        recommendation="hold",
        status="analysed",
        strengths="Terraform, Docker",
        missing_skills="Kubernetes at scale",
        ai_summary=json.dumps({
            "matched_skills": "Terraform, Python",
            "missing_skills": "Kubernetes",
            "match_score": 82.0,
            "recommendation_label": "Review",
        }),
    )
    r3 = Resume(
        job_posting_id=job.id,
        candidate_name="Charlie Coder",
        candidate_email="charlie@cloud.example",
        file_name="charlie_cv.pdf",
        file_path="obj:recruitment-resumes/charlie.pdf",
        extracted_text="Junior developer with basic Python knowledge.",
        ai_score=42.0,
        recommendation="rejected",
        status="analysed",
        strengths="Python basics",
        missing_skills="AWS, Kubernetes, Terraform",
        ai_summary=json.dumps({
            "matched_skills": "Python",
            "missing_skills": "AWS, Kubernetes, Terraform",
            "match_score": 42.0,
            "recommendation_label": "Not Recommended",
        }),
    )
    r4 = Resume(
        job_posting_id=job.id,
        candidate_name="David Draft",
        candidate_email="david@cloud.example",
        file_name="david_cv.pdf",
        file_path="obj:recruitment-resumes/david.pdf",
        extracted_text="Unprocessed resume text.",
        status="extracted",
    )
    db.add_all([r1, r2, r3, r4])
    db.commit()

    # Query top 2 candidates
    res = client.get(f"{BASE}/jobs/{job.id}/top-candidates?top_n=2", headers=hr_user["headers"])
    assert res.status_code == 200, res.text
    top2 = res.json()
    assert len(top2) == 2

    # Check rank order and score descending
    assert top2[0]["candidate_name"] == "Alice Architect"
    assert top2[0]["rank"] == 1
    assert top2[0]["ai_score"] == 94.5
    assert top2[0]["meets_criteria"] is True
    assert top2[0]["application_status"] == "Shortlisted"
    assert "AWS" in top2[0]["matched_skills"]

    assert top2[1]["candidate_name"] == "Bob Builder"
    assert top2[1]["rank"] == 2
    assert top2[1]["ai_score"] == 82.0
    assert top2[1]["meets_criteria"] is True
    assert top2[1]["application_status"] == "Under Review"

    # Query top 10 (fewer than 10 exist, should return all 4 without error)
    res_all = client.get(f"{BASE}/jobs/{job.id}/top-candidates?top_n=10", headers=hr_user["headers"])
    assert res_all.status_code == 200
    all_cands = res_all.json()
    assert len(all_cands) == 4
    # Check Charlie has meets_criteria=False because score is 42 < 50
    charlie_entry = next(c for c in all_cands if c["candidate_name"] == "Charlie Coder")
    assert charlie_entry["meets_criteria"] is False
    assert charlie_entry["application_status"] == "Rejected"

    # Check David (unanalysed) is ranked after scored candidates
    david_entry = next(c for c in all_cands if c["candidate_name"] == "David Draft")
    assert david_entry["rank"] == 4
    assert david_entry["meets_criteria"] is False
    assert david_entry["application_status"] == "Screening"

    # Validation: top_n < 1 returns 422
    assert client.get(f"{BASE}/jobs/{job.id}/top-candidates?top_n=0", headers=hr_user["headers"]).status_code in (400, 422)

    # RBAC: plain employee cannot access recruitment ranking (403)
    assert client.get(f"{BASE}/jobs/{job.id}/top-candidates?top_n=5", headers=plain_user["headers"]).status_code == 403


def test_interview_invitation_email_and_audit(client, db, new_user):
    tag = uuid.uuid4().hex[:8]
    hr_user = new_user("Recruiter HR", role="hr_manager")
    plain_user = new_user("Plain User", role="employee")

    # Create Job & Resume
    job = JobPosting(
        title=f"Staff Fullstack Engineer {tag}",
        description="Lead frontend & backend engineering",
        required_skills="React, Node.js, Python, PostgreSQL",
        created_by=hr_user["id"],
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    resume = Resume(
        job_posting_id=job.id,
        candidate_name="Elena Rostova",
        candidate_email=f"elena_{tag}@candidate.example",
        file_name="elena_resume.pdf",
        file_path="obj:recruitment-resumes/elena.pdf",
        extracted_text="Fullstack developer with 6 years experience in React and Python.",
        ai_score=91.0,
        recommendation="selected",
        status="analysed",
        ai_summary=json.dumps({
            "matched_skills": "React, Python",
            "match_score": 91.0,
            "recommendation_label": "Strong Match",
        }),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    # 1. Send interview invitation
    invite_payload = {
        "recipient_email": f"elena_{tag}@candidate.example",
        "candidate_name": "Elena Rostova",
        "job_position": job.title,
        "interview_date": "2026-11-15",
        "interview_time": "14:30 IST",
        "interview_mode": "Google Meet (meet.google.com/abc-defg-hij)",
        "email_subject": f"Interview Invitation for {job.title} at EnterpriseAI",
        "email_body": (
            "Dear Elena,\n\n"
            "We were impressed by your resume and would love to invite you for an interview."
        ),
    }

    r = client.post(
        f"{BASE}/resumes/{resume.id}/interview-invite",
        headers=hr_user["headers"],
        json=invite_payload,
    )
    assert r.status_code == 200, r.text
    res_data = r.json()
    assert res_data["status"] == "success"
    assert res_data["recipient_email"] == f"elena_{tag}@candidate.example"
    assert res_data["application_status"] == "Interview Scheduled"

    # 2. Check resume metadata was updated
    db.refresh(resume)
    detail = json.loads(resume.ai_summary)
    assert detail["interview_invited"] is True
    assert detail["interview_details"]["interview_date"] == "2026-11-15"
    assert detail["interview_details"]["interview_mode"] == "Google Meet (meet.google.com/abc-defg-hij)"

    # 3. Check top-candidates reflects "Interview Scheduled"
    r_top = client.get(f"{BASE}/jobs/{job.id}/top-candidates?top_n=5", headers=hr_user["headers"])
    assert r_top.status_code == 200
    cands = r_top.json()
    elena = next(c for c in cands if c["resume_id"] == resume.id)
    assert elena["interview_invited"] is True
    assert elena["application_status"] == "Interview Scheduled"

    # 4. Check audit log has entry
    audit_row = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "recruitment.interview_invitation_sent",
            AuditLog.entity_id == str(resume.id),
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_row is not None
    assert audit_row.actor_user_id == hr_user["id"]
    assert audit_row.after["candidate_name"] == "Elena Rostova"
    assert audit_row.after["interview_date"] == "2026-11-15"

    # 5. RBAC: non-HR employee cannot send invitation (403)
    r_forbid = client.post(
        f"{BASE}/resumes/{resume.id}/interview-invite",
        headers=plain_user["headers"],
        json=invite_payload,
    )
    assert r_forbid.status_code == 403
