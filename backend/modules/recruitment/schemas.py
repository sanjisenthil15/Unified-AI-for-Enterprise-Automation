"""
modules/recruitment/schemas.py

Pydantic schemas for the Recruitment module.
Phase 2 adds AnalysisResult and updates ResumeResponse / ResumeListItem.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# Job Posting schemas
# ------------------------------------------------------------------ #

class JobPostingCreate(BaseModel):
    title:            str = Field(..., min_length=3, max_length=150)
    description:      Optional[str] = None
    required_skills:  str = Field(..., description="Comma-separated skills")
    min_education:    str = Field(default="Bachelor's Degree")
    experience_level: str = Field(default="mid", pattern="^(entry|junior|mid|senior|lead)$")


class JobPostingUpdate(BaseModel):
    title:            Optional[str] = Field(None, min_length=3, max_length=150)
    description:      Optional[str] = None
    required_skills:  Optional[str] = None
    min_education:    Optional[str] = None
    experience_level: Optional[str] = Field(None, pattern="^(entry|junior|mid|senior|lead)$")


class JobPostingResponse(BaseModel):
    id:               int
    title:            str
    description:      Optional[str]
    required_skills:  str
    min_education:    str
    experience_level: str
    status:           str
    created_by:       int
    created_at:       datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ #
# Resume schemas
# ------------------------------------------------------------------ #

class ResumeResponse(BaseModel):
    """Full resume record including AI analysis fields."""
    id:              int
    job_posting_id:  int
    candidate_name:  str
    candidate_email: Optional[str]
    file_name:       str
    status:          str
    extracted_text:  Optional[str]  = None
    ai_score:        Optional[float] = None
    ai_summary:      Optional[str]  = None   # stores full JSON detail in Phase 2
    strengths:       Optional[str]  = None
    missing_skills:  Optional[str]  = None
    recommendation:  Optional[str]  = None
    created_at:      datetime

    model_config = {"from_attributes": True}


class ResumeListItem(BaseModel):
    """Lightweight resume entry used in list/results table."""
    id:             int
    candidate_name: str
    candidate_email: Optional[str] = None
    file_name:      str
    status:         str
    ai_score:       Optional[float] = None
    ai_summary:     Optional[str]   = None   # JSON detail
    strengths:      Optional[str]   = None
    missing_skills: Optional[str]   = None
    recommendation: Optional[str]   = None
    created_at:     datetime

    model_config = {"from_attributes": True}


class ResumeUpdate(BaseModel):
    """Allow HR to correct auto-extracted candidate info only."""
    candidate_name:  Optional[str] = Field(None, min_length=1, max_length=120)
    candidate_email: Optional[str] = Field(None, max_length=255)


class BulkUploadFileResult(BaseModel):
    file_name:        str
    status:           str           # ok | error | duplicate
    resume_id:        Optional[int] = None
    candidate_name:   Optional[str] = None
    candidate_email:  Optional[str] = None
    extraction_status: Optional[str] = None
    error:            Optional[str] = None


class BulkUploadResponse(BaseModel):
    job_id:    int
    total:     int
    succeeded: int
    failed:    int
    duplicates: int
    files:     List[BulkUploadFileResult]


class RecruitmentStats(BaseModel):
    open_positions: int
    applications:   int
    waiting:        int
    shortlisted:    int
    rejected:       int


# ------------------------------------------------------------------ #
# AI analysis response
# ------------------------------------------------------------------ #

class AnalysisResponse(BaseModel):
    """
    Returned by POST /jobs/{job_id}/analyze.
    Contains a list of updated resume results.
    """
    job_id:   int
    analysed: int               # how many resumes were newly analysed
    results:  List[ResumeListItem]
