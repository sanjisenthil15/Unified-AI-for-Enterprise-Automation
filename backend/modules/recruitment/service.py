"""
modules/recruitment/service.py

Business logic for the Recruitment module.

Phase 1: PDF upload, text extraction, job CRUD
Phase 2: Gemini AI resume analysis (added here)
"""

import io
import json
import re
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from config.settings import settings
from models.job_posting import JobPosting
from models.resume      import Resume

# ------------------------------------------------------------------ #
# File storage
# ------------------------------------------------------------------ #
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "resumes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ #
# PDF text extraction
# ------------------------------------------------------------------ #

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using PyPDF2."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
        return "\n\n".join(pages_text)
    except Exception as exc:
        print(f"[RecruitmentService] PDF extraction failed: {exc}")
        return ""


# ------------------------------------------------------------------ #
# Job Posting CRUD
# ------------------------------------------------------------------ #

def create_job_posting(db: Session, payload, created_by_id: int) -> JobPosting:
    """Create and persist a new job posting."""
    job = JobPosting(
        title=payload.title,
        description=payload.description,
        required_skills=payload.required_skills,
        min_education=payload.min_education,
        experience_level=payload.experience_level,
        created_by=created_by_id,
        status="active",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_job_postings(db: Session, skip: int = 0, limit: int = 50):
    """Return all active job postings, newest first."""
    return (
        db.query(JobPosting)
        .filter(JobPosting.status != "closed")
        .order_by(JobPosting.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_job_posting(db: Session, job_id: int) -> JobPosting:
    """Fetch a single job posting or raise 404."""
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job posting id={job_id} not found.",
        )
    return job


# ------------------------------------------------------------------ #
# Resume upload + text extraction
# ------------------------------------------------------------------ #

def save_and_extract_resume(
    db: Session,
    job_id: int,
    candidate_name: str,
    candidate_email: str | None,
    upload_file: UploadFile,
) -> Resume:
    """Save PDF to disk, extract text, persist Resume row."""
    if not upload_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only PDF files are accepted. Got: {upload_file.filename}",
        )
    file_bytes  = upload_file.file.read()
    unique_name = f"{uuid.uuid4().hex}_{upload_file.filename}"
    file_path   = UPLOAD_DIR / unique_name
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    extracted = extract_text_from_pdf(file_bytes)
    extraction_status = "extracted" if extracted.strip() else "error"

    resume = Resume(
        job_posting_id  = job_id,
        candidate_name  = candidate_name,
        candidate_email = candidate_email,
        file_name       = upload_file.filename,
        file_path       = str(file_path),
        extracted_text  = extracted,
        status          = extraction_status,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def list_resumes_for_job(db: Session, job_id: int):
    """Return all resumes for a job posting, newest first."""
    return (
        db.query(Resume)
        .filter(Resume.job_posting_id == job_id)
        .order_by(Resume.created_at.desc())
        .all()
    )


def get_resume(db: Session, resume_id: int) -> Resume:
    """Fetch a single resume by ID or raise 404."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume id={resume_id} not found.",
        )
    return resume


# ------------------------------------------------------------------ #
# Gemini AI analysis (Phase 2)
# ------------------------------------------------------------------ #

def _build_prompt(job: JobPosting, resume_text: str) -> str:
    """
    Build the Gemini prompt.

    Fairness rule: for entry/junior jobs, academic projects and relevant
    skills count as evidence of capability — lack of company experience
    must NOT automatically lower the score.
    """
    fresher_note = ""
    if job.experience_level in ("entry", "junior"):
        fresher_note = (
            "\n\nFAIRNESS NOTE: This is an entry-level / fresher position. "
            "Academic projects, coursework, personal projects, and relevant skills "
            "should be weighted positively. Do NOT penalise the candidate solely "
            "because they have no professional work experience."
        )

    return f"""You are an expert recruitment AI. Analyse the candidate resume against the job requirements and return a JSON object ONLY — no markdown, no explanation, just the raw JSON.

JOB REQUIREMENTS:
Title: {job.title}
Required Skills: {job.required_skills}
Minimum Education: {job.min_education}
Experience Level: {job.experience_level}
Description: {job.description or 'N/A'}
{fresher_note}

CANDIDATE RESUME TEXT:
{resume_text[:4000]}

Return EXACTLY this JSON structure (no extra keys, no markdown):
{{
  "match_score": <integer 0-100 based on skills 50%, education 15%, experience 20%, projects/domain 15%>,
  "recommendation": "<one of: Strong Match | Good Match | Review | Not Recommended>",
  "matched_skills": "<comma-separated skills found in resume>",
  "missing_skills": "<comma-separated required skills NOT found in resume>",
  "education_match": "<Yes / Partial / No — with one-line reason>",
  "experience_match": "<Yes / Partial / No — with one-line reason>",
  "strengths": "<2-3 key strengths observed>",
  "concerns": "<2-3 concerns or gaps, if any — write None if no concerns>",
  "short_reason": "<2-3 sentence overall assessment>"
}}"""


def _map_recommendation(rec_str: str) -> str:
    """
    Map Gemini recommendation text to the DB ENUM values.
    DB allows: selected | hold | rejected
    """
    r = rec_str.lower()
    if "strong" in r or "good" in r:
        return "selected"
    if "review" in r:
        return "hold"
    return "rejected"


def analyze_resume_with_gemini(db: Session, resume: Resume, job: JobPosting) -> Resume:
    """
    Send the resume text + job requirements to Gemini, parse the response,
    and save the results to the existing Resume row.

    Uses google-genai SDK (modern API).
    Raises HTTPException on configuration or API errors.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API key is not configured.",
        )

    if not resume.extracted_text or not resume.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Resume id={resume.id} has no extracted text to analyse.",
        )

    # Call Gemini
    try:
        from google import genai                          # modern SDK
        client   = genai.Client(api_key=api_key)
        prompt   = _build_prompt(job, resume.extracted_text)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        raw_text = response.text.strip()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini API error: {exc}",
        )

    # Parse JSON — strip markdown fences if present
    clean = re.sub(r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini returned non-JSON response: {raw_text[:300]}",
        )

    # Save results to existing Resume record
    resume.ai_score       = float(data.get("match_score", 0))
    resume.ai_summary     = data.get("short_reason", "")
    resume.strengths      = data.get("strengths", "")
    resume.missing_skills = data.get("missing_skills", "")
    resume.recommendation = _map_recommendation(data.get("recommendation", ""))
    resume.status         = "analysed"

    # Store full detail fields as JSON in ai_summary (reuse Text column)
    full_detail = {
        "recommendation_label": data.get("recommendation", ""),
        "matched_skills":       data.get("matched_skills", ""),
        "missing_skills":       data.get("missing_skills", ""),
        "education_match":      data.get("education_match", ""),
        "experience_match":     data.get("experience_match", ""),
        "strengths":            data.get("strengths", ""),
        "concerns":             data.get("concerns", ""),
        "short_reason":         data.get("short_reason", ""),
        "match_score":          data.get("match_score", 0),
    }
    resume.ai_summary = json.dumps(full_detail)

    db.commit()
    db.refresh(resume)
    return resume


def analyze_job_resumes(db: Session, job_id: int) -> list:
    """
    Analyse all extracted resumes for a job posting.
    Skips resumes that have already been analysed or have no text.
    Returns the list of updated Resume objects.
    """
    job = get_job_posting(db, job_id)
    resumes = (
        db.query(Resume)
        .filter(
            Resume.job_posting_id == job_id,
            Resume.status == "extracted",        # only un-analysed resumes
        )
        .all()
    )
    if not resumes:
        # If all already analysed, return existing results
        return list_resumes_for_job(db, job_id)

    results = []
    for resume in resumes:
        try:
            updated = analyze_resume_with_gemini(db, resume, job)
            results.append(updated)
        except HTTPException:
            raise
        except Exception as exc:
            # Mark as error but continue with next resume
            resume.status = "error"
            resume.ai_summary = json.dumps({"error": str(exc)})
            db.commit()
            results.append(resume)

    return results
