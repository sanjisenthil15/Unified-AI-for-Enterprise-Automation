/**
 * api/notificationsApi.js
 *
 * Notifications module — all API calls (plus the escalation endpoints,
 * which feed the same notification system).
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/notifications';

export async function getMyNotifications({ unreadOnly, category, limit, beforeId } = {}) {
  const res = await axiosInstance.get(`${BASE}/me`, {
    params: {
      unread_only: unreadOnly, category: category || undefined, limit, before_id: beforeId,
    },
  });
  return res.data;
}

export async function getUnreadCount() {
  const res = await axiosInstance.get(`${BASE}/unread-count`);
  return res.data;
}

export async function markNotificationRead(notificationId) {
  const res = await axiosInstance.post(`${BASE}/${notificationId}/read`);
  return res.data;
}

export async function markAllNotificationsRead({ category } = {}) {
  const res = await axiosInstance.post(`${BASE}/read-all`, null, { params: { category: category || undefined } });
  return res.data;
}

/** Admin / HR Manager. */
export async function listEscalations({ status } = {}) {
  const res = await axiosInstance.get('/api/v1/escalations', { params: { status: status || undefined } });
  return res.data;
}

/** Admin only. */
export async function runEscalationSweep() {
  const res = await axiosInstance.post('/api/v1/escalations/run');
  return res.data;
}
