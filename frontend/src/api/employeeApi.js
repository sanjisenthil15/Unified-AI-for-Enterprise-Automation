/**
 * api/employeeApi.js
 *
 * Employee Management module — all API calls.
 * Goes through the shared axiosInstance (JWT attached automatically).
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/employee-management';

/** The caller's own employee record. Throws (404) if not yet onboarded. */
export async function getMyEmployeeRecord() {
  const res = await axiosInstance.get(`${BASE}/me`);
  return res.data;
}

export async function listDepartments() {
  const res = await axiosInstance.get(`${BASE}/departments`);
  return res.data;
}

export async function createDepartment({ name, description }) {
  const res = await axiosInstance.post(`${BASE}/departments`, { name, description });
  return res.data;
}

export async function listEmployees({ departmentId, status } = {}) {
  const res = await axiosInstance.get(`${BASE}/employees`, {
    params: { department_id: departmentId, status_filter: status },
  });
  return res.data;
}

export async function getEmployee(id) {
  const res = await axiosInstance.get(`${BASE}/employees/${id}`);
  return res.data;
}

/**
 * Onboards a new hire — creates their login account and employee record
 * together. Returns { employee, temporary_password } — the password is
 * only ever shown this once.
 */
export async function createEmployee({
  fullName, email, roleId, jobTitle, departmentId, projectId, phone, hireDate, employmentType,
}) {
  const res = await axiosInstance.post(`${BASE}/employees`, {
    full_name: fullName,
    email,
    role_id: roleId,
    job_title: jobTitle,
    department_id: departmentId || null,
    project_id: projectId || null,
    phone: phone || null,
    hire_date: hireDate,
    employment_type: employmentType || 'full_time',
  });
  return res.data;
}

export async function updateEmployee(id, { jobTitle, departmentId, projectId, phone, employmentType, status }) {
  const payload = {};
  if (jobTitle !== undefined) payload.job_title = jobTitle;
  if (departmentId !== undefined) payload.department_id = departmentId;
  if (projectId !== undefined) payload.project_id = projectId;
  if (phone !== undefined) payload.phone = phone;
  if (employmentType !== undefined) payload.employment_type = employmentType;
  if (status !== undefined) payload.status = status;
  const res = await axiosInstance.patch(`${BASE}/employees/${id}`, payload);
  return res.data;
}

export async function terminateEmployee(id) {
  const res = await axiosInstance.post(`${BASE}/employees/${id}/terminate`);
  return res.data;
}

export async function listProjects() {
  const res = await axiosInstance.get(`${BASE}/projects`);
  return res.data;
}

export async function getProject(projectId) {
  const res = await axiosInstance.get(`${BASE}/projects/${projectId}`);
  return res.data;
}

export async function listProjectMembers(projectId) {
  const res = await axiosInstance.get(`${BASE}/projects/${projectId}/members`);
  return res.data;
}

export async function createProject({ name, description, startDate, deadline, status }) {
  const payload = { name, description: description || null, deadline: deadline || null };
  if (startDate) payload.start_date = startDate;
  if (status) payload.status = status;
  const res = await axiosInstance.post(`${BASE}/projects`, payload);
  return res.data;
}

export async function updateProject(projectId, { name, description, startDate, deadline }) {
  const payload = {};
  if (name !== undefined) payload.name = name;
  if (description !== undefined) payload.description = description;
  if (startDate !== undefined) payload.start_date = startDate;
  if (deadline !== undefined) payload.deadline = deadline;
  const res = await axiosInstance.patch(`${BASE}/projects/${projectId}`, payload);
  return res.data;
}

export async function updateProjectStatus(projectId, status) {
  const res = await axiosInstance.patch(`${BASE}/projects/${projectId}/status`, { status });
  return res.data;
}

export async function deleteProject(projectId) {
  const res = await axiosInstance.delete(`${BASE}/projects/${projectId}`);
  return res.data;
}

export async function assignTeamLead(projectId, employeeId) {
  const res = await axiosInstance.post(`${BASE}/projects/${projectId}/team-lead`, { employee_id: employeeId });
  return res.data;
}

export async function assignProjectManager(projectId, managerUserId) {
  const res = await axiosInstance.post(`${BASE}/projects/${projectId}/manager`, { manager_user_id: managerUserId });
  return res.data;
}
