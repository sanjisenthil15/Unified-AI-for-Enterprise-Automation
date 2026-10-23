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
  fullName, email, roleId, jobTitle, departmentId, phone, hireDate, employmentType,
}) {
  const res = await axiosInstance.post(`${BASE}/employees`, {
    full_name: fullName,
    email,
    role_id: roleId,
    job_title: jobTitle,
    department_id: departmentId || null,
    phone: phone || null,
    hire_date: hireDate,
    employment_type: employmentType || 'full_time',
  });
  return res.data;
}

export async function updateEmployee(id, { jobTitle, departmentId, phone, employmentType, status }) {
  const payload = {};
  if (jobTitle !== undefined) payload.job_title = jobTitle;
  if (departmentId !== undefined) payload.department_id = departmentId;
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
