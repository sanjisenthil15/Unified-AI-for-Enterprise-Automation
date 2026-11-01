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
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from config.settings import settings
from models.job_posting import JobPosting
from models.resume      import Resume
from core import audit
from models.candidate import Candidate
from modules.recruitment.schemas import (
    InterviewInviteRequest,
    InterviewInviteResponse,
    TopCandidateResponse,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# File storage
# ------------------------------------------------------------------ #
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "resumes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Resumes are read fully into memory for text extraction — cap them so one
# upload can't exhaust a small instance's RAM.
MAX_RESUME_BYTES = 10 * 1024 * 1024
_SAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


class ResumeFileError(ValueError):
    """An uploaded resume failed validation (message is safe to show)."""


# Resume.file_path for files in permanent object storage:
#   "obj:<bucket>/<key>"   e.g. "obj:recruitment-resumes/job_4/3f2a…_cv.pdf"
# Rows from before object storage keep their original local disk path.
OBJECT_REF_PREFIX = "obj:"


def resume_object_ref(file_path: str | None) -> tuple[str, str] | None:
    """(bucket, key) for an object-storage resume, else None (legacy local path)."""
    if not file_path or not file_path.startswith(OBJECT_REF_PREFIX):
        return None
    bucket, _, key = file_path[len(OBJECT_REF_PREFIX):].partition("/")
    return (bucket, key) if bucket and key else None


def _store_resume_pdf(job_id: int, safe_name: str, file_bytes: bytes) -> tuple[str, str]:
    """Upload to the private resumes bucket; returns (bucket, key)."""
    from core.object_storage import get_object_storage, unique_key

    bucket = settings.STORAGE_BUCKET_RESUMES
    key = unique_key(f"job_{int(job_id)}", filename=safe_name)
    get_object_storage().upload_bytes(bucket, key, file_bytes, "application/pdf")
    return bucket, key


def _discard_object(bucket: str, key: str) -> None:
    from core.object_storage import ObjectStorageError, get_object_storage

    try:
        get_object_storage().delete(bucket, [key])
    except ObjectStorageError:
        print(f"[RecruitmentService] Orphaned resume object left for cleanup: {bucket}/{key}")


def _read_validated_pdf(upload_file: UploadFile) -> tuple[str, bytes]:
    """Return (safe stored-name suffix, bytes) for a genuine, size-capped PDF.

    The client-supplied filename never reaches the filesystem as-is: only
    its final path component is kept, restricted to safe characters, so
    names like '../../x.pdf' or 'a/b.pdf' can't escape UPLOAD_DIR.
    """
    original = upload_file.filename or ""
    if not original.lower().endswith(".pdf"):
        raise ResumeFileError(f"Only PDF files are accepted. Got: {original}")
    file_bytes = upload_file.file.read(MAX_RESUME_BYTES + 1)
    if len(file_bytes) > MAX_RESUME_BYTES:
        raise ResumeFileError(f"'{original}' is larger than {MAX_RESUME_BYTES // (1024 * 1024)} MB.")
    if not file_bytes.startswith(b"%PDF-"):
        raise ResumeFileError(f"'{original}' is not a valid PDF file.")
    base = original.replace("\\", "/").rsplit("/", 1)[-1]
    safe = _SAFE_NAME_CHARS.sub("_", base).strip(" .") or "resume.pdf"
    return safe[-120:], file_bytes


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
    try:
        safe_name, file_bytes = _read_validated_pdf(upload_file)
    except ResumeFileError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    from core.object_storage import ObjectStorageError

    # Bytes go to permanent storage first; the row is only committed once
    # they're safely stored, and the object is removed if the commit fails.
    try:
        bucket, key = _store_resume_pdf(job_id, safe_name, file_bytes)
    except ObjectStorageError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    extracted = extract_text_from_pdf(file_bytes)
    extraction_status = "extracted" if extracted.strip() else "error"

    resume = Resume(
        job_posting_id  = job_id,
        candidate_name  = candidate_name,
        candidate_email = candidate_email,
        file_name       = upload_file.filename,
        file_path       = f"{OBJECT_REF_PREFIX}{bucket}/{key}",
        extracted_text  = extracted,
        status          = extraction_status,
    )
    try:
        db.add(resume)
        db.commit()
    except Exception:
        db.rollback()
        _discard_object(bucket, key)
        raise
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
    from core.object_storage import ObjectStorageError

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

            try:
                safe_name, file_bytes = _read_validated_pdf(upload_file)
            except ResumeFileError as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)
                results.append(entry)
                continue
            try:
                bucket, key = _store_resume_pdf(job_id, safe_name, file_bytes)
            except ObjectStorageError as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)
                results.append(entry)
                continue

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
                file_path       = f"{OBJECT_REF_PREFIX}{bucket}/{key}",
                extracted_text  = extracted,
                status          = extraction_status,
            )
            try:
                db.add(resume)
                db.commit()
            except Exception:
                db.rollback()
                _discard_object(bucket, key)
                raise
            db.refresh(resume)

            entry["resume_id"]        = resume.id
            entry["candidate_name"]   = candidate_name
            entry["candidate_email"]  = candidate_email
            entry["extraction_status"] = extraction_status
        except Exception:
            db.rollback()
            entry["status"] = "error"
            entry["error"]  = "Could not save this resume. Please try again."
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
    ref = resume_object_ref(resume.file_path)
    db.delete(resume)
    db.commit()
    # Remove the file only after the row is gone, so a failed commit never
    # leaves a record pointing at a deleted file.
    if ref is not None:
        _discard_object(*ref)
    else:
        try:
            p = Path(resume.file_path)
            if p.exists():
                p.unlink()
        except Exception as exc:
            print(f"[RecruitmentService] Could not delete file {resume.file_path}: {exc}")


def resume_download_url(db: Session, resume_id: int) -> dict:
    """Short-lived signed URL for the original PDF (caller authorizes)."""
    from core.object_storage import ObjectStorageError, get_object_storage

    resume = get_resume(db, resume_id)
    ref = resume_object_ref(resume.file_path)
    ttl = settings.SIGNED_URL_TTL_SECONDS
    if ref is None:
        # Legacy upload from before object storage: only reachable while the
        # file still exists in the local resumes folder of this machine.
        legacy = Path(resume.file_path or "")
        try:
            inside = legacy.resolve().parent == UPLOAD_DIR.resolve()
        except OSError:
            inside = False
        if settings.STORAGE_BACKEND != "local" or not inside or not legacy.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The original PDF of this older upload is no longer available; its extracted text is kept.",
            )
        ref = (settings.STORAGE_BUCKET_RESUMES, legacy.name)
    try:
        url = get_object_storage().signed_url(ref[0], ref[1], ttl)
    except ObjectStorageError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"url": url, "expires_in": ttl, "file_name": resume.file_name}


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
            results.append(resume)  # end_analyze_resumes

    return results



# ------------------------------------------------------------------ #
# Top-N Candidate Ranking and Interview Invitation Workflow
# ------------------------------------------------------------------ #

def get_top_ranked_candidates(db: Session, job_id: int, top_n: int = 5) -> list[TopCandidateResponse]:
    """
    Returns the top N candidates for a job posting ranked by AI match score descending.
    Differentiates candidates who meet screening criteria (score >= 50, strong/review recommendation)
    from unanalyzed, missing OCR, or low-scoring candidates.
    Gracefully handles fewer candidates than top_n.
    """
    if top_n < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="top_n must be a positive integer >= 1.",
        )

    # Ensure job posting exists (raises 404 if not)
    get_job_posting(db, job_id)

    resumes = db.query(Resume).filter(Resume.job_posting_id == job_id).all()
    if not resumes:
        return []

    scored = []
    unscored = []

    for r in resumes:
        detail = {}
        if r.ai_summary:
            try:
                detail = json.loads(r.ai_summary)
            except Exception:
                detail = {"short_reason": r.ai_summary}

        interview_invited = bool(detail.get("interview_invited", False))
        interview_sent_at = detail.get("interview_sent_at")
        interview_details = detail.get("interview_details")
        matched_skills = detail.get("matched_skills") or r.strengths
        missing_skills = detail.get("missing_skills") or r.missing_skills

        # Determine application status
        if interview_invited:
            app_status = "Interview Scheduled"
        elif r.recommendation == "selected":
            app_status = "Shortlisted"
        elif r.recommendation == "hold":
            app_status = "Under Review"
        elif r.recommendation == "rejected":
            app_status = "Rejected"
        elif r.status == "analysed":
            app_status = "Analysed"
        elif r.status == "extracted":
            app_status = "Screening"
        elif r.status == "error":
            app_status = "Extraction Error"
        else:
            app_status = "Applied"

        # Check screening criteria
        is_analyzed = (r.status == "analysed" and r.ai_score is not None)
        meets = bool(is_analyzed and (r.ai_score or 0) >= 50 and r.recommendation in ("selected", "hold"))

        item_data = {
            "resume": r,
            "ocr_status": r.status,
            "ai_score": r.ai_score,
            "recommendation": r.recommendation,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "application_status": app_status,
            "interview_invited": interview_invited,
            "interview_sent_at": interview_sent_at,
            "interview_details": interview_details,
            "meets_criteria": meets,
        }

        if is_analyzed:
            scored.append(item_data)
        else:
            unscored.append(item_data)

    # Sort scored candidates by match score descending
    scored.sort(key=lambda x: (x["ai_score"] or 0.0), reverse=True)
    # Unscored sorted by created_at desc
    unscored.sort(key=lambda x: x["resume"].created_at, reverse=True)

    combined = scored + unscored
    top_slice = combined[:top_n]

    results = []
    for rank_idx, item in enumerate(top_slice, start=1):
        r = item["resume"]
        results.append(TopCandidateResponse(
            rank=rank_idx,
            resume_id=r.id,
            candidate_name=r.candidate_name,
            candidate_email=r.candidate_email,
            file_name=r.file_name,
            ocr_status=item["ocr_status"],
            ai_score=item["ai_score"],
            recommendation=item["recommendation"],
            matched_skills=item["matched_skills"],
            missing_skills=item["missing_skills"],
            application_status=item["application_status"],
            interview_invited=item["interview_invited"],
            interview_sent_at=item["interview_sent_at"],
            interview_details=item["interview_details"],
            meets_criteria=item["meets_criteria"],
        ))

    return results


def send_interview_invitation(
    db: Session,
    resume_id: int,
    payload: InterviewInviteRequest,
    current_user,
) -> InterviewInviteResponse:
    """
    Sends an interview invitation email to the candidate.
    Uses SMTP if configured; otherwise logs and simulates delivery safely.
    Updates candidate / resume status and logs an audit trail event.
    """
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resume id={resume_id} not found.",
        )

    # Parse existing summary JSON
    detail = {}
    if resume.ai_summary:
        try:
            detail = json.loads(resume.ai_summary)
        except Exception:
            detail = {"short_reason": resume.ai_summary}

    already_invited = bool(detail.get("interview_invited", False))

    # Send email via SMTP if configured, else simulate
    simulated = True
    if settings.SMTP_HOST and settings.SMTP_PORT:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = payload.recipient_email
            msg["Subject"] = payload.email_subject
            msg.attach(MIMEText(payload.email_body, "plain"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_EMAIL, [payload.recipient_email], msg.as_string())
            simulated = False
            logger.info("Successfully sent interview invitation email to %s via SMTP", payload.recipient_email)
        except Exception as exc:
            logger.warning("SMTP delivery failed (%s); falling back to simulated delivery", exc)
            simulated = True
    else:
        logger.info(
            "SMTP not configured; simulated email to %s: Subject=%r",
            payload.recipient_email, payload.email_subject,
        )

    now = datetime.now(timezone.utc)

    # Update resume metadata
    detail["interview_invited"] = True
    detail["interview_sent_at"] = now.isoformat()
    detail["interview_details"] = {
        "candidate_name": payload.candidate_name,
        "job_position": payload.job_position,
        "interview_date": payload.interview_date,
        "interview_time": payload.interview_time,
        "interview_mode": payload.interview_mode,
        "recipient_email": payload.recipient_email,
        "subject": payload.email_subject,
        "sent_by_user_id": current_user.id,
        "simulated": simulated,
    }
    resume.ai_summary = json.dumps(detail)

    # Update or sync Candidate table if available
    cand = (
        db.query(Candidate)
        .filter(
            (Candidate.email == payload.recipient_email)
            | ((Candidate.job_posting_id == resume.job_posting_id) & (Candidate.full_name == resume.candidate_name))
        )
        .first()
    )
    if cand:
        cand.status = "interview"

    # Record audit log event
    audit.record_event(
        db,
        "recruitment.interview_invitation_sent",
        "resume",
        resume.id,
        actor=current_user,
        before={"interview_invited": already_invited},
        after={
            "candidate_name": payload.candidate_name,
            "recipient_email": payload.recipient_email,
            "job_position": payload.job_position,
            "interview_date": payload.interview_date,
            "interview_time": payload.interview_time,
            "interview_mode": payload.interview_mode,
            "simulated": simulated,
            "already_invited": already_invited,
        },
    )

    db.commit()
    db.refresh(resume)

    msg_suffix = " (simulated delivery; SMTP unconfigured)" if simulated else ""
    return InterviewInviteResponse(
        status="success",
        message=f"Interview invitation sent to {payload.recipient_email}{msg_suffix}.",
        resume_id=resume.id,
        recipient_email=payload.recipient_email,
        sent_at=now,
        application_status="Interview Scheduled",
        simulated=simulated,
    )
