/**
 * api/chatApi.js
 *
 * Manager Chat module — all API calls.
 */

import axiosInstance from './axiosInstance';

const BASE = '/api/v1/chat';

export async function getContacts() {
  const res = await axiosInstance.get(`${BASE}/contacts`);
  return res.data;
}

export async function openThread(otherUserId) {
  const res = await axiosInstance.post(`${BASE}/threads`, { other_user_id: otherUserId });
  return res.data;
}

export async function listThreads() {
  const res = await axiosInstance.get(`${BASE}/threads`);
  return res.data;
}

export async function getMessages(threadId, sinceId) {
  const res = await axiosInstance.get(`${BASE}/threads/${threadId}/messages`, {
    params: { since_id: sinceId },
  });
  return res.data;
}

export async function sendMessage(threadId, body) {
  const res = await axiosInstance.post(`${BASE}/threads/${threadId}/messages`, { body });
  return res.data;
}

export async function markThreadRead(threadId) {
  const res = await axiosInstance.post(`${BASE}/threads/${threadId}/read`);
  return res.data;
}
