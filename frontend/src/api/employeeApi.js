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

export async function createProject({ name, description }) {
  const res = await axiosInstance.post(`${BASE}/projects`, { name, description });
  return res.data;
}

export async function assignTeamLead(projectId, employeeId) {
  const res = await axiosInstance.post(`${BASE}/projects/${projectId}/team-lead`, { employee_id: employeeId });
  return res.data;
}
