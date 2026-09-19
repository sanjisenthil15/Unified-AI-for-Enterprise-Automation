/**
 * api/incidentApi.js
 * Incident Management — all API calls.
 * JWT auto-attached via axiosInstance interceptor.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/incidents';

// ── Statistics ────────────────────────────────────────────────────
export async function getIncidentStats() {
  const res = await axiosInstance.get(`${BASE}/statistics`);
  return res.data;
}

// ── List / Get ────────────────────────────────────────────────────
export async function listIncidents(params = {}) {
  const res = await axiosInstance.get(BASE, { params });
  return res.data;
}

export async function getIncident(id) {
  const res = await axiosInstance.get(`${BASE}/${id}`);
  return res.data;
}

// ── Create / Update / Delete ──────────────────────────────────────
export async function createIncident(payload) {
  const res = await axiosInstance.post(BASE, payload);
  return res.data;
}

export async function updateIncident(id, payload) {
  const res = await axiosInstance.put(`${BASE}/${id}`, payload);
  return res.data;
}

export async function deleteIncident(id) {
  await axiosInstance.delete(`${BASE}/${id}`);
}

// ── Lifecycle ─────────────────────────────────────────────────────
export async function updateIncidentStatus(id, status, notes = '') {
  const res = await axiosInstance.put(`${BASE}/${id}/status`, { status, notes });
  return res.data;
}

export async function assignIncident(id, assignedTo, notes = '') {
  const res = await axiosInstance.put(`${BASE}/${id}/assign`, {
    assigned_to: assignedTo,
    notes,
  });
  return res.data;
}

export async function resolveIncident(id, rootCause, notes = '') {
  const res = await axiosInstance.put(`${BASE}/${id}/resolve`, {
    root_cause: rootCause,
    notes,
  });
  return res.data;
}

export async function closeIncident(id) {
  const res = await axiosInstance.put(`${BASE}/${id}/close`);
  return res.data;
}

// ── AI Triage ─────────────────────────────────────────────────────
export async function runAITriage(id) {
  const res = await axiosInstance.post(`${BASE}/${id}/triage`);
  return res.data;
}

export async function getLatestTriage(id) {
  const res = await axiosInstance.get(`${BASE}/${id}/triage`);
  return res.data;
}

// ── Timeline ──────────────────────────────────────────────────────
export async function getTimeline(id) {
  const res = await axiosInstance.get(`${BASE}/${id}/timeline`);
  return res.data;
}
