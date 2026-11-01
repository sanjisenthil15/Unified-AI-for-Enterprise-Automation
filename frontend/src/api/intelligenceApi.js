/**
 * api/intelligenceApi.js
 *
 * AI Intelligence module — API client for executive summaries, project risks,
 * sprint delay analysis, workload bottlenecks, operations insights, and cache refresh.
 * Goes through the shared axiosInstance which attaches the JWT automatically.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/intelligence';

/**
 * GET /api/v1/intelligence/executive-summary
 * Restricted to Admin and Manager roles.
 * Returns ExecutiveSummaryResponse.
 */
export async function getExecutiveSummary() {
  const res = await axiosInstance.get(`${BASE}/executive-summary`);
  return res.data;
}

/**
 * GET /api/v1/intelligence/project-risks
 * Admin & Manager can query all or filter by project_id.
 * Team Leaders must supply their assigned project_id.
 * Returns ProjectRiskIntelligenceResponse.
 */
export async function getProjectRisks(projectId = null) {
  const params = {};
  if (projectId !== null && projectId !== undefined && projectId !== '') {
    params.project_id = Number(projectId);
  }
  const res = await axiosInstance.get(`${BASE}/project-risks`, { params });
  return res.data;
}

/**
 * GET /api/v1/intelligence/sprint-delays
 * Admin & Manager can query all or filter by project_id / sprint_id.
 * Team Leaders can only query sprints for their assigned project.
 * Returns SprintDelayIntelligenceResponse.
 */
export async function getSprintDelays(projectId = null, sprintId = null) {
  const params = {};
  if (projectId !== null && projectId !== undefined && projectId !== '') {
    params.project_id = Number(projectId);
  }
  if (sprintId !== null && sprintId !== undefined && sprintId !== '') {
    params.sprint_id = Number(sprintId);
  }
  const res = await axiosInstance.get(`${BASE}/sprint-delays`, { params });
  return res.data;
}

/**
 * GET /api/v1/intelligence/workload-bottlenecks
 * Identifies workload imbalances at team/role level without individual surveillance.
 * Returns WorkloadIntelligenceResponse.
 */
export async function getWorkloadBottlenecks(projectId = null) {
  const params = {};
  if (projectId !== null && projectId !== undefined && projectId !== '') {
    params.project_id = Number(projectId);
  }
  const res = await axiosInstance.get(`${BASE}/workload-bottlenecks`, { params });
  return res.data;
}

/**
 * GET /api/v1/intelligence/operations-insights
 * Cross-module synthesis of support friction and incident patterns.
 * Restricted to Admin and Manager roles.
 * Returns OperationsInsightsResponse.
 */
export async function getOperationsInsights() {
  const res = await axiosInstance.get(`${BASE}/operations-insights`);
  return res.data;
}

/**
 * POST /api/v1/intelligence/refresh
 * Invalidates intelligence cache and recalculates insights.
 * Throttled to 10-second cooldown per scope; returns HTTP 429 when active.
 *
 * @param {{ scope?: 'org' | 'project', projectId?: number|null }} options
 * @returns {Promise<{ status: string, message: string, scope: string, project_id?: number }>}
 */
export async function refreshIntelligence({ scope = 'org', projectId = null } = {}) {
  const payload = {
    scope: projectId ? 'project' : scope,
    project_id: projectId ? Number(projectId) : null,
  };
  const res = await axiosInstance.post(`${BASE}/refresh`, payload);
  return res.data;
}
