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


def update_job_posting(db: Session, job_id: int, payload) -> JobPosting:
    """Update an existing job posting's editable fields."""
    job = get_job_posting(db, job_id)
    if payload.title is not None:
        job.title = payload.title
    if payload.description is not None:
        job.description = payload.description
    if payload.required_skills is not None:
        job.required_skills = payload.required_skills
    if payload.min_education is not None:
        job.min_education = payload.min_education
    if payload.experience_level is not None:
        job.experience_level = payload.experience_level
    db.commit()
    db.refresh(job)
    return job


def delete_job_posting(db: Session, job_id: int) -> None:
    """Soft-close a job posting (set status=closed). Does not delete resumes."""
    job = get_job_posting(db, job_id)
    job.status = "closed"
    db.commit()


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


# ------------------------------------------------------------------ #
# Auto-extract candidate name + email from raw PDF text
# ------------------------------------------------------------------ #

def _auto_extract_candidate_info(text: str) -> dict:
    """
    Best-effort extraction of candidate name and email from resume text.
    Returns {"name": str|None, "email": str|None}.
    Does NOT invent information — returns None when not found.

    Strategy:
      - Email: scan the top 30 lines for a valid email pattern, prefer
        the first found in the header. Fall back to first valid email
        anywhere in the document.
      - Name: scan the top 20 lines only. Strict filters reject section
        headings, skill lists, school/institution names, URLs, and lines
        containing digits or disqualifying punctuation.
    """
    EMAIL_RE = re.compile(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    )
    JUNK_EMAIL_RE = re.compile(
        r"(noreply|no-reply|example|support@|info@|admin@|donotreply)",
        re.IGNORECASE,
    )

    # Words whose presence disqualifies a line from being a name
    REJECT_WORDS = {
        # resume section headings
        "curriculum", "vitae", "resume", "cv", "profile", "contact",
        "summary", "objective", "education", "experience", "skills",
        "technical", "projects", "certifications", "references",
        "address", "phone", "email", "linkedin", "github", "mobile",
        "tel", "fax", "website", "portfolio", "achievements",
        "internship", "work", "professional", "declaration", "date",
        "place", "nationality", "hobbies", "interests", "languages",
        # institution / school words
        "school", "college", "university", "institute", "institution",
        "matric", "higher", "secondary", "academy", "polytechnic",
        "engineering", "technology", "science", "arts", "commerce",
        "management", "studies", "department", "faculty",
        # tech / programming terms
        "python", "java", "javascript", "typescript", "html", "css",
        "sql", "react", "node", "angular", "vue", "django", "flask",
        "fastapi", "spring", "docker", "git", "linux", "aws", "azure",
        "gcp", "mysql", "mongodb", "redis", "kotlin", "swift",
        "flutter", "dart", "rust", "golang", "scala", "matlab",
        "tableau", "powerbi", "excel", "hadoop", "spark",
    }

    # Characters that signal this is NOT a name line
    PUNCT_REJECT = set(':,/|@#•→►▸–—*[](){}<>_~`')

    lines = text.splitlines()
    header_lines = [l.strip() for l in lines[:30] if l.strip()]

    # ── Email ────────────────────────────────────────────────────────
    email = None
    for line in header_lines:
        m = EMAIL_RE.search(line)
        if m and not JUNK_EMAIL_RE.search(m.group(0)):
            email = m.group(0).strip()
            break
    if not email:
        for m in EMAIL_RE.finditer(text):
            addr = m.group(0).strip()
            if not JUNK_EMAIL_RE.search(addr):
                email = addr
                break

    # ── Name ─────────────────────────────────────────────────────────
    name = None

    def _normalize_dotted(line: str) -> str:
        """
        Turn dotted-initial tokens like 'SNEHA.T.D' into 'SNEHA T D'
        so they can be tokenized as separate words.
        """
        # Replace a dot between a letter and another letter with a space
        return re.sub(r'(?<=[A-Za-z])\.(?=[A-Za-z])', ' ', line)

    for raw_line in header_lines[:20]:
        line = _normalize_dotted(raw_line).strip()

        if EMAIL_RE.search(line):
            continue
        if re.search(r'\d', line):
            continue
        if any(ch in PUNCT_REJECT for ch in line):
            continue
        if re.search(r'https?://|www\.|linkedin\.com|github\.com', line, re.IGNORECASE):
            continue
        if len(line) < 3 or len(line) > 55:
            continue

        words = line.split()
        if not (2 <= len(words) <= 5):
            continue

        # Every word must start with a letter
        if not all(w[0].isalpha() for w in words):
            continue

        # Each word must be purely alphabetic (allows single initials like "R")
        if not all(re.match(r'^[A-Za-z]+$', w) for w in words):
            continue

        # Reject if any word is in the reject list
        if any(w.lower() in REJECT_WORDS for w in words):
            continue

        # Must have at least one word with 3+ letters (not just initials)
        long_words = [w for w in words if len(w) >= 3]
        if not long_words:
            continue

        # At least one long word must look like a proper noun
        # (title-case, all-caps, or mixed-case starting with uppercase)
        proper = [
            w for w in long_words
            if w[0].isupper()
        ]
        if not proper:
            continue

        name = " ".join(words)
        break

    return {"name": name, "email": email}


# ------------------------------------------------------------------ #
# Bulk upload — process multiple files, one failure won't stop others
# ------------------------------------------------------------------ #

def bulk_upload_resumes(
    db: Session,
    job_id: int,
    files: list,          # list of UploadFile
) -> list:
    """
    Process multiple PDF uploads for a single job.
    Auto-extracts candidate name + email from each PDF.
    Returns list of dicts with result per file.
    """
    get_job_posting(db, job_id)   # raise 404 early if job missing
    results = []
    for upload_file in files:
        entry = {"file_name": upload_file.filename, "status": "ok", "resume_id": None,
                 "candidate_name": None, "candidate_email": None, "error": None,
                 "extraction_status": None}
        try:
            if not upload_file.filename.lower().endswith(".pdf"):
                entry["status"] = "error"
                entry["error"] = "Not a PDF file"
                results.append(entry)
                continue

            # Duplicate check — same filename already uploaded for this job
            existing = (
                db.query(Resume)
                .filter(Resume.job_posting_id == job_id, Resume.file_name == upload_file.filename)
                .first()
            )
            if existing:
                entry["status"] = "duplicate"
                entry["error"] = f"File '{upload_file.filename}' already uploaded for this job."
                entry["resume_id"] = existing.id
                results.append(entry)
                continue

            file_bytes = upload_file.file.read()
            unique_name = f"{uuid.uuid4().hex}_{upload_file.filename}"
            file_path = UPLOAD_DIR / unique_name
            with open(file_path, "wb") as f:
                f.write(file_bytes)

            extracted = extract_text_from_pdf(file_bytes)
            extraction_status = "extracted" if extracted.strip() else "error"

            # Auto-detect name + email
            info = _auto_extract_candidate_info(extracted) if extracted.strip() else {"name": None, "email": None}
            candidate_name  = info["name"]  or "Not detected"
            candidate_email = info["email"]

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

            entry["resume_id"]        = resume.id
            entry["candidate_name"]   = candidate_name
            entry["candidate_email"]  = candidate_email
            entry["extraction_status"] = extraction_status
        except Exception as exc:
            entry["status"] = "error"
            entry["error"]  = str(exc)
        results.append(entry)
    return results


# ------------------------------------------------------------------ #
# Edit resume candidate info
# ------------------------------------------------------------------ #

def update_resume_info(db: Session, resume_id: int, payload) -> Resume:
    """Allow HR to correct auto-extracted candidate name / email."""
    resume = get_resume(db, resume_id)
    if payload.candidate_name is not None:
        resume.candidate_name = payload.candidate_name
    if payload.candidate_email is not None:
        resume.candidate_email = payload.candidate_email
    db.commit()
    db.refresh(resume)
    return resume


# ------------------------------------------------------------------ #
# Delete resume
# ------------------------------------------------------------------ #

def delete_resume(db: Session, resume_id: int) -> None:
    """Delete a resume record and its file from disk."""
    resume = get_resume(db, resume_id)
    # Remove file from disk if it exists
    try:
        p = Path(resume.file_path)
        if p.exists():
            p.unlink()
    except Exception as exc:
        print(f"[RecruitmentService] Could not delete file {resume.file_path}: {exc}")
    db.delete(resume)
    db.commit()


# ------------------------------------------------------------------ #
# Recruitment statistics
# ------------------------------------------------------------------ #

def get_recruitment_stats(db: Session) -> dict:
    """Return real counts from the database for the stats banner."""
    from sqlalchemy import func as sqlfunc
    open_positions = db.query(JobPosting).filter(JobPosting.status == "active").count()
    total_resumes  = db.query(Resume).count()
    waiting        = db.query(Resume).filter(Resume.status == "extracted").count()
    shortlisted    = db.query(Resume).filter(Resume.recommendation == "selected").count()
    rejected       = db.query(Resume).filter(Resume.recommendation == "rejected").count()
    return {
        "open_positions": open_positions,
        "applications":   total_resumes,
        "waiting":        waiting,
        "shortlisted":    shortlisted,
        "rejected":       rejected,
    }


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
