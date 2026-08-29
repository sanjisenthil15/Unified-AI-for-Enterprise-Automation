"""
modules/recruitment/router.py

FastAPI router for the AI Recruitment module.

Endpoints:
    POST   /recruitment/jobs                        — Create job posting (HR/admin)
    GET    /recruitment/jobs                        — List all job postings
    GET    /recruitment/jobs/{job_id}               — Get a single job posting
    POST   /recruitment/jobs/{job_id}/resumes       — Upload PDF + extract text
    GET    /recruitment/jobs/{job_id}/resumes       — List resumes for a job
    GET    /recruitment/resumes/{resume_id}         — Get single resume
    POST   /recruitment/jobs/{job_id}/analyze       — Run Gemini AI on all resumes (Phase 2)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_user, require_roles
from models.user import User

from modules.recruitment.schemas import (
    AnalysisResponse,
    JobPostingCreate,
    JobPostingResponse,
    ResumeListItem,
    ResumeResponse,
)
from modules.recruitment import service

router = APIRouter(prefix="/recruitment", tags=["Recruitment"])


# ------------------------------------------------------------------ #
# Job Posting endpoints
# ------------------------------------------------------------------ #

@router.post("/jobs", response_model=JobPostingResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a new job posting (HR / Admin only)")
def create_job(
    payload:      JobPostingCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(["hr", "admin"])),
):
    return service.create_job_posting(db, payload, created_by_id=current_user.id)


@router.get("/jobs", response_model=List[JobPostingResponse],
            summary="List all active job postings")
def list_jobs(
    skip: int = 0, limit: int = 50,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.list_job_postings(db, skip=skip, limit=limit)


@router.get("/jobs/{job_id}", response_model=JobPostingResponse,
            summary="Get a single job posting")
def get_job(
    job_id:       int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.get_job_posting(db, job_id)


# ------------------------------------------------------------------ #
# Resume endpoints
# ------------------------------------------------------------------ #

@router.post("/jobs/{job_id}/resumes", response_model=ResumeResponse,
             status_code=status.HTTP_201_CREATED,
             summary="Upload PDF resume and extract text (HR / Admin only)")
async def upload_resume(
    job_id:          int,
    candidate_name:  str            = Form(...),
    candidate_email: Optional[str]  = Form(None),
    resume_file:     UploadFile     = File(...),
    db:              Session        = Depends(get_db),
    current_user:    User           = Depends(require_roles(["hr", "admin"])),
):
    service.get_job_posting(db, job_id)
    return service.save_and_extract_resume(
        db=db, job_id=job_id,
        candidate_name=candidate_name, candidate_email=candidate_email,
        upload_file=resume_file,
    )


@router.get("/jobs/{job_id}/resumes", response_model=List[ResumeListItem],
            summary="List all resumes for a job posting")
def list_resumes(
    job_id:       int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    service.get_job_posting(db, job_id)
    return service.list_resumes_for_job(db, job_id)


@router.get("/resumes/{resume_id}", response_model=ResumeResponse,
            summary="Get a single resume with extracted text")
def get_resume(
    resume_id:    int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    return service.get_resume(db, resume_id)


# ------------------------------------------------------------------ #
# Phase 2 — Gemini AI analysis
# ------------------------------------------------------------------ #

@router.post(
    "/jobs/{job_id}/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Gemini AI analysis on all extracted resumes for a job (HR / Admin only)",
)
def analyze_resumes(
    job_id:       int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_roles(["hr", "admin"])),
):
    """
    Analyses every resume with status='extracted' for the given job posting.
    Sends extracted text + job requirements to Gemini, parses the structured
    response, and saves results to the resumes table.

    Returns the full updated resume list for the job so the frontend
    can re-render the results table in one round-trip.
    """
    results = service.analyze_job_resumes(db, job_id)
    analysed_count = sum(1 for r in results if r.status == "analysed")
    return AnalysisResponse(
        job_id=job_id,
        analysed=analysed_count,
        results=results,
    )
