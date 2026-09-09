/**
 * api/meetingApi.js
 *
 * Meeting Intelligence module — all API calls.
 * Goes through the shared axiosInstance (JWT attached automatically,
 * 401 -> redirect to /login).
 *
 * Backend routes (all under /api/v1, JWT required, scoped to the caller):
 *   POST   /meetings                     upload a recorded meeting
 *   GET    /meetings                     meeting history
 *   GET    /meetings/{id}                details + processing status
 *   GET    /meetings/{id}/transcript     transcript + speakers + segments
 *   GET    /meetings/{id}/analysis       summary / key points / decisions
 *   GET    /meetings/{id}/action-items   extracted action items
 *   DELETE /meetings/{id}                delete meeting + files
 */

import axiosInstance from './axiosInstance';

/** Accepted upload extensions (mirrors the backend allow-list). */
export const ACCEPTED_EXTENSIONS = [
  '.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v',
  '.mp3', '.wav', '.m4a', '.aac', '.flac',
];

/**
 * POST /api/v1/meetings  (multipart)
 * @param {{ title: string, description?: string, meetingDate?: string, file: File }} payload
 * @returns {Promise<object>} the created meeting (status = "pending")
 */
export async function uploadMeeting({ title, description, meetingDate, file }) {
  const form = new FormData();
  form.append('title', title);
  if (description) form.append('description', description);
  if (meetingDate) form.append('meeting_date', meetingDate);
  form.append('file', file);

  const res = await axiosInstance.post('/api/v1/meetings', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function listMeetings({ skip = 0, limit = 50 } = {}) {
  const res = await axiosInstance.get('/api/v1/meetings', { params: { skip, limit } });
  return res.data;
}

export async function getMeeting(id) {
  const res = await axiosInstance.get(`/api/v1/meetings/${id}`);
  return res.data;
}

export async function getTranscript(id) {
  const res = await axiosInstance.get(`/api/v1/meetings/${id}/transcript`);
  return res.data;
}

export async function getAnalysis(id) {
  const res = await axiosInstance.get(`/api/v1/meetings/${id}/analysis`);
  return res.data;
}

export async function getActionItems(id) {
  const res = await axiosInstance.get(`/api/v1/meetings/${id}/action-items`);
  return res.data;
}

export async function reprocessMeeting(id) {
  const res = await axiosInstance.post(`/api/v1/meetings/${id}/reprocess`);
  return res.data;
}

export async function deleteMeeting(id) {
  await axiosInstance.delete(`/api/v1/meetings/${id}`);
}
