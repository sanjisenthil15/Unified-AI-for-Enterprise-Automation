/**
 * api/sprintsApi.js
 *
 * Sprints module — all API calls (sprints, tasks, manager review, burndown).
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/sprints';

export async function listSprints(projectId) {
  const res = await axiosInstance.get(BASE, { params: { project_id: projectId } });
  return res.data;
}

export async function createSprint({ projectId, name, startDate, endDate }) {
  const res = await axiosInstance.post(BASE, {
    project_id: projectId, name, start_date: startDate, end_date: endDate,
  });
  return res.data;
}

export async function getSprint(sprintId) {
  const res = await axiosInstance.get(`${BASE}/${sprintId}`);
  return res.data;
}

export async function updateSprint(sprintId, { name, startDate, endDate, status } = {}) {
  const payload = {};
  if (name !== undefined) payload.name = name;
  if (startDate !== undefined) payload.start_date = startDate;
  if (endDate !== undefined) payload.end_date = endDate;
  if (status !== undefined) payload.status = status;
  const res = await axiosInstance.patch(`${BASE}/${sprintId}`, payload);
  return res.data;
}

export async function listTasks(sprintId) {
  const res = await axiosInstance.get(`${BASE}/${sprintId}/tasks`);
  return res.data;
}

export async function createTask(sprintId, { title, description, assigneeId, dueDate }) {
  const res = await axiosInstance.post(`${BASE}/${sprintId}/tasks`, {
    title, description: description || null, assignee_id: assigneeId || null, due_date: dueDate || null,
  });
  return res.data;
}

export async function updateTask(taskId, { status, progressPercent, description, title, assigneeId, dueDate } = {}) {
  const payload = {};
  if (status !== undefined) payload.status = status;
  if (progressPercent !== undefined) payload.progress_percent = progressPercent;
  if (description !== undefined) payload.description = description;
  if (title !== undefined) payload.title = title;
  if (assigneeId !== undefined) payload.assignee_id = assigneeId;
  if (dueDate !== undefined) payload.due_date = dueDate;
  const res = await axiosInstance.patch(`${BASE}/tasks/${taskId}`, payload);
  return res.data;
}

export async function getMyTasks({ status } = {}) {
  const res = await axiosInstance.get(`${BASE}/tasks/me`, { params: { status_filter: status } });
  return res.data;
}

export async function getManagerReview({ projectId, startDate, endDate }) {
  const res = await axiosInstance.get(`${BASE}/review`, {
    params: { project_id: projectId, start_date: startDate, end_date: endDate },
  });
  return res.data;
}

export async function getBurndown(sprintId) {
  const res = await axiosInstance.get(`${BASE}/${sprintId}/burndown`);
  return res.data;
}

export async function generateWeeklySprints(projectId) {
  const res = await axiosInstance.post(`${BASE}/generate-weekly`, { project_id: projectId });
  return res.data;
}

export async function getEnterpriseOverview() {
  const res = await axiosInstance.get(`${BASE}/overview`);
  return res.data;
}
