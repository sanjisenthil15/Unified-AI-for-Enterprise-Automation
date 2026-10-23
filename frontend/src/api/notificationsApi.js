/**
 * api/notificationsApi.js
 *
 * Notifications module — all API calls.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/notifications';

export async function getMyNotifications({ unreadOnly } = {}) {
  const res = await axiosInstance.get(`${BASE}/me`, { params: { unread_only: unreadOnly } });
  return res.data;
}

export async function markNotificationRead(notificationId) {
  const res = await axiosInstance.post(`${BASE}/${notificationId}/read`);
  return res.data;
}

export async function markAllNotificationsRead() {
  const res = await axiosInstance.post(`${BASE}/read-all`);
  return res.data;
}
