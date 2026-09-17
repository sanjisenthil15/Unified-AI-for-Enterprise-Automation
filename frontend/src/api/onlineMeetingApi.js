import api from './axiosInstance';

const BASE = '/api/v1/meetings/online';

export async function startOnlineMeeting(title, requestId) {
  return (await api.post(BASE, { title, request_id: requestId }, { timeout: 15000 })).data;
}

export async function getOnlineMeeting(id) {
  return (await api.get(`${BASE}/${encodeURIComponent(id)}`, { timeout: 15000 })).data;
}

export async function endOnlineMeeting(id) {
  return (await api.post(`${BASE}/${encodeURIComponent(id)}/end`, {}, { timeout: 15000 })).data;
}

export async function getOnlineTicket(id) {
  return (await api.post(`${BASE}/${encodeURIComponent(id)}/ws-ticket`, {}, { timeout: 15000 })).data;
}

export function onlineSocketUrl(id) {
  const url = new URL(`${BASE}/${encodeURIComponent(id)}/ws`, api.defaults.baseURL);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}