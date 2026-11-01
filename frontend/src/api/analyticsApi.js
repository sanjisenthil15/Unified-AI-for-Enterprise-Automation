/**
 * api/analyticsApi.js
 *
 * Analytics Dashboard module — API client for executive overviews,
 * project performance, workforce analytics, operations, and trends.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/analytics';

export async function getAnalyticsOverview() {
  const res = await axiosInstance.get(`${BASE}/overview`);
  return res.data;
}

export async function getProjectAnalytics(projectId = null) {
  const params = projectId ? { project_id: projectId } : {};
  const res = await axiosInstance.get(`${BASE}/projects`, { params });
  return res.data;
}

export async function getWorkforceAnalytics(projectId = null) {
  const params = projectId ? { project_id: projectId } : {};
  const res = await axiosInstance.get(`${BASE}/workforce`, { params });
  return res.data;
}

export async function getOperationsAnalytics() {
  const res = await axiosInstance.get(`${BASE}/operations`);
  return res.data;
}

export async function getAnalyticsTrends(rangeDays = 14, projectId = null) {
  const params = { range_days: rangeDays };
  if (projectId) params.project_id = projectId;
  const res = await axiosInstance.get(`${BASE}/trends`, { params });
  return res.data;
}
