/**
 * api/recruitmentApi.js
 *
 * Axios calls for the Recruitment module.
 * All requests go through axiosInstance which auto-attaches the JWT.
 */

import axiosInstance from './axiosInstance';

// ── Job Postings ──────────────────────────────────────────────────

/** POST /api/v1/recruitment/jobs — create a new job posting */
export async function createJob(payload) {
  const res = await axiosInstance.post('/api/v1/recruitment/jobs', payload);
  return res.data;
}

/** GET /api/v1/recruitment/jobs — list all active job postings */
export async function listJobs() {
  const res = await axiosInstance.get('/api/v1/recruitment/jobs');
  return res.data;
}

/** GET /api/v1/recruitment/jobs/:id — get a single job posting */
export async function getJob(jobId) {
  const res = await axiosInstance.get(`/api/v1/recruitment/jobs/${jobId}`);
  return res.data;
}

// ── Resumes ───────────────────────────────────────────────────────

/**
 * POST /api/v1/recruitment/jobs/:jobId/resumes
 * Upload a single PDF resume with candidate metadata.
 * Uses multipart/form-data.
 */
export async function uploadResume(jobId, candidateName, candidateEmail, file) {
  const form = new FormData();
  form.append('candidate_name',  candidateName);
  form.append('candidate_email', candidateEmail || '');
  form.append('resume_file',     file);

  const res = await axiosInstance.post(
    `/api/v1/recruitment/jobs/${jobId}/resumes`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return res.data;
}

/** GET /api/v1/recruitment/jobs/:jobId/resumes — list resumes for a job */
export async function listResumes(jobId) {
  const res = await axiosInstance.get(`/api/v1/recruitment/jobs/${jobId}/resumes`);
  return res.data;
}

/** GET /api/v1/recruitment/resumes/:id — get full resume with extracted text */
export async function getResume(resumeId) {
  const res = await axiosInstance.get(`/api/v1/recruitment/resumes/${resumeId}`);
  return res.data;
}

/**
 * POST /api/v1/recruitment/jobs/:jobId/analyze
 * Run Gemini AI analysis on all extracted resumes for a job.
 * Returns { job_id, analysed, results: ResumeListItem[] }
 */
export async function analyzeResumes(jobId) {
  const res = await axiosInstance.post(`/api/v1/recruitment/jobs/${jobId}/analyze`);
  return res.data;
}
