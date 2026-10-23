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

// ── Groups & channels ──────────────────────────────────────────────

export async function createGroup({ projectId, name, memberUserIds }) {
  const res = await axiosInstance.post(`${BASE}/groups`, {
    project_id: projectId, name, member_user_ids: memberUserIds || [],
  });
  return res.data;
}

export async function listGroups() {
  const res = await axiosInstance.get(`${BASE}/groups`);
  return res.data;
}

export async function getGroupDetail(groupId) {
  const res = await axiosInstance.get(`${BASE}/groups/${groupId}`);
  return res.data;
}

export async function addGroupMember(groupId, userId) {
  await axiosInstance.post(`${BASE}/groups/${groupId}/members`, { user_id: userId });
}

export async function removeGroupMember(groupId, userId) {
  await axiosInstance.delete(`${BASE}/groups/${groupId}/members/${userId}`);
}

export async function createChannel(groupId, name) {
  const res = await axiosInstance.post(`${BASE}/groups/${groupId}/channels`, { name });
  return res.data;
}

export async function listGroupChannels(groupId) {
  const res = await axiosInstance.get(`${BASE}/groups/${groupId}/channels`);
  return res.data;
}

export async function getChannelMessages(channelId, sinceId) {
  const res = await axiosInstance.get(`${BASE}/channels/${channelId}/messages`, {
    params: { since_id: sinceId },
  });
  return res.data;
}

export async function sendChannelMessage(channelId, body) {
  const res = await axiosInstance.post(`${BASE}/channels/${channelId}/messages`, { body });
  return res.data;
}

export async function markChannelRead(channelId) {
  const res = await axiosInstance.post(`${BASE}/channels/${channelId}/read`);
  return res.data;
}
