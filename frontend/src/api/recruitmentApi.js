/**
 * api/recruitmentApi.js
 * Recruitment module — all API calls.
 * Auto-attaches JWT via axiosInstance interceptor.
 */

import axiosInstance from './axiosInstance';

// ── Job Postings ──────────────────────────────────────────────────

export async function createJob(payload) {
  const res = await axiosInstance.post('/api/v1/recruitment/jobs', payload);
  return res.data;
}

export async function listJobs() {
  const res = await axiosInstance.get('/api/v1/recruitment/jobs');
  return res.data;
}

export async function getJob(jobId) {
  const res = await axiosInstance.get(`/api/v1/recruitment/jobs/${jobId}`);
  return res.data;
}

export async function updateJob(jobId, payload) {
  const res = await axiosInstance.put(`/api/v1/recruitment/jobs/${jobId}`, payload);
  return res.data;
}

export async function deleteJob(jobId) {
  await axiosInstance.delete(`/api/v1/recruitment/jobs/${jobId}`);
}

// ── Resumes ───────────────────────────────────────────────────────

/** Single upload — still used for manual override if needed */
export async function uploadResume(jobId, candidateName, candidateEmail, file) {
  const form = new FormData();
  form.append('candidate_name',  candidateName);
  form.append('candidate_email', candidateEmail || '');
  form.append('resume_file',     file);
  const res = await axiosInstance.post(
    `/api/v1/recruitment/jobs/${jobId}/resumes`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return res.data;
}

/**
 * Bulk upload — auto-extracts name + email from each PDF.
 * `files` is a FileList or Array of File objects.
 */
export async function bulkUploadResumes(jobId, files) {
  const form = new FormData();
  Array.from(files).forEach(f => form.append('files', f));
  const res = await axiosInstance.post(
    `/api/v1/recruitment/jobs/${jobId}/resumes/bulk`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return res.data;
}

export async function listResumes(jobId) {
  const res = await axiosInstance.get(`/api/v1/recruitment/jobs/${jobId}/resumes`);
  return res.data;
}

export async function getResume(resumeId) {
  const res = await axiosInstance.get(`/api/v1/recruitment/resumes/${resumeId}`);
  return res.data;
}

export async function updateResume(resumeId, payload) {
  const res = await axiosInstance.put(`/api/v1/recruitment/resumes/${resumeId}`, payload);
  return res.data;
}

export async function deleteResume(resumeId) {
  await axiosInstance.delete(`/api/v1/recruitment/resumes/${resumeId}`);
}

// ── AI analysis ───────────────────────────────────────────────────

export async function analyzeResumes(jobId) {
  const res = await axiosInstance.post(`/api/v1/recruitment/jobs/${jobId}/analyze`);
  return res.data;
}

// ── Stats ─────────────────────────────────────────────────────────

export async function getRecruitmentStats() {
  const res = await axiosInstance.get('/api/v1/recruitment/stats');
  return res.data;
}
