/**
 * api/leaveApi.js
 *
 * Leave Approval module — all API calls.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/leave';

export async function getLeaveTypes() {
  const res = await axiosInstance.get(`${BASE}/types`);
  return res.data;
}

export async function submitLeaveRequest({ leaveType, startDate, endDate, reason }) {
  const res = await axiosInstance.post(`${BASE}/requests`, {
    leave_type: leaveType, start_date: startDate, end_date: endDate, reason,
  });
  return res.data;
}

export async function getMyLeaveRequests() {
  const res = await axiosInstance.get(`${BASE}/requests/me`);
  return res.data;
}

export async function cancelLeaveRequest(requestId) {
  const res = await axiosInstance.post(`${BASE}/requests/${requestId}/cancel`);
  return res.data;
}

/** Admin / HR Manager only. */
export async function listLeaveRequests({ status, employeeId } = {}) {
  const res = await axiosInstance.get(`${BASE}/requests`, {
    params: { status: status || undefined, employee_id: employeeId || undefined },
  });
  return res.data;
}

export async function approveLeaveRequest(requestId, note) {
  const res = await axiosInstance.post(`${BASE}/requests/${requestId}/approve`, { note: note || null });
  return res.data;
}

export async function rejectLeaveRequest(requestId, reason) {
  const res = await axiosInstance.post(`${BASE}/requests/${requestId}/reject`, { reason });
  return res.data;
}
