/**
 * api/attendanceApi.js
 *
 * Attendance module — all API calls.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/attendance';

export async function checkIn() {
  const res = await axiosInstance.post(`${BASE}/check-in`);
  return res.data;
}

export async function checkOut() {
  const res = await axiosInstance.post(`${BASE}/check-out`);
  return res.data;
}

export async function getMyAttendance({ startDate, endDate } = {}) {
  const res = await axiosInstance.get(`${BASE}/me`, {
    params: { start_date: startDate, end_date: endDate },
  });
  return res.data;
}

export async function getTeamAttendance({ projectId, startDate, endDate }) {
  const res = await axiosInstance.get(`${BASE}/team`, {
    params: { project_id: projectId, start_date: startDate, end_date: endDate },
  });
  return res.data;
}

export async function getEmployeeAttendance(employeeId, { startDate, endDate } = {}) {
  const res = await axiosInstance.get(`${BASE}/employee/${employeeId}`, {
    params: { start_date: startDate, end_date: endDate },
  });
  return res.data;
}
