/**
 * api/customerSupportApi.js
 *
 * Comprehensive API client for the Enterprise Customer Support AI Platform.
 * All requests route through the configured axiosInstance with automatic JWT Bearer auth.
 */

import axiosInstance from './axiosInstance.js';

// ── 1. Module Health & Operational Stats ──────────────────────────────

export async function getCustomerSupportHealth() {
  const res = await axiosInstance.get('/api/v1/customer-support/health');
  return res.data;
}

export async function getCustomerSupportStats() {
  const res = await axiosInstance.get('/api/v1/customer-support/stats');
  return res.data;
}

export async function globalSupportSearch(query, limit = 15) {
  const res = await axiosInstance.get('/api/v1/customer-support/global-search', {
    params: { q: query, limit },
  });
  return res.data;
}

// ── 2. Knowledge Base & BM25 Search ───────────────────────────────────

export async function searchKnowledgeBase(query, categoryId = null, docType = null, minScore = 0.15, limit = 5) {
  const params = { q: query, min_score: minScore, limit };
  if (categoryId) params.category_id = categoryId;
  if (docType) params.doc_type = docType;
  const res = await axiosInstance.get('/api/v1/customer-support/knowledge/search', { params });
  return res.data;
}

export async function listKnowledgeDocuments(params = {}) {
  const res = await axiosInstance.get('/api/v1/customer-support/knowledge', { params });
  return res.data;
}

export async function getKnowledgeDocument(documentId) {
  const res = await axiosInstance.get(`/api/v1/customer-support/knowledge/${documentId}`);
  return res.data;
}

export async function listCategories() {
  const res = await axiosInstance.get('/api/v1/customer-support/categories');
  return res.data;
}

export async function listTeams() {
  const res = await axiosInstance.get('/api/v1/customer-support/teams');
  return res.data;
}

// ── 3. AI Chat Sessions & Grounded Chatbot ────────────────────────────

export async function createChatSession(payload = {}) {
  const res = await axiosInstance.post('/api/v1/customer-support/chat/sessions', payload);
  return res.data;
}

export async function listChatSessions(limit = 30) {
  const res = await axiosInstance.get('/api/v1/customer-support/chat/sessions', { params: { limit } });
  return res.data;
}

export async function getChatSession(sessionId) {
  const res = await axiosInstance.get(`/api/v1/customer-support/chat/sessions/${sessionId}`);
  return res.data;
}

export async function deleteChatSession(sessionId) {
  const res = await axiosInstance.delete(`/api/v1/customer-support/chat/sessions/${sessionId}`);
  return res.data;
}

export async function sendChatMessage(sessionId, message, customerName = null, customerEmail = null) {
  const payload = {
    session_id: sessionId,
    message: message,
    customer_name: customerName,
    customer_email: customerEmail,
  };
  const res = await axiosInstance.post('/api/v1/customer-support/chat/message', payload);
  return res.data;
}

export async function submitChatFeedback(messageId, rating, comment = null) {
  const payload = { rating, comment };
  const res = await axiosInstance.post(`/api/v1/customer-support/chat/messages/${messageId}/feedback`, payload);
  return res.data;
}

export async function generateAgentHandoff(sessionId) {
  const res = await axiosInstance.post('/api/v1/customer-support/chat/handoff', null, {
    params: { session_id: sessionId },
  });
  return res.data;
}

// ── 4. Support Ticket Management ──────────────────────────────────────

export async function listTickets(params = {}) {
  const res = await axiosInstance.get('/api/v1/customer-support/tickets', { params });
  return res.data;
}

export async function getTicket(ticketId) {
  const res = await axiosInstance.get(`/api/v1/customer-support/tickets/${ticketId}`);
  return res.data;
}

export async function createTicket(ticketData) {
  const res = await axiosInstance.post('/api/v1/customer-support/tickets', ticketData);
  return res.data;
}

export async function updateTicket(ticketId, updateData) {
  const res = await axiosInstance.put(`/api/v1/customer-support/tickets/${ticketId}`, updateData);
  return res.data;
}

export async function addTicketMessage(ticketId, message, isAi = false) {
  const res = await axiosInstance.post(`/api/v1/customer-support/tickets/${ticketId}/messages`, {
    message,
    is_ai: isAi,
  });
  return res.data;
}

export async function escalateChatToTicket(payload) {
  const res = await axiosInstance.post('/api/v1/customer-support/tickets/escalate', payload);
  return res.data;
}

// ── 5. Enterprise Service Status & Incident Telemetry ─────────────────

export async function getServiceStatuses() {
  const res = await axiosInstance.get('/api/v1/customer-support/services/status');
  return res.data;
}

export async function listIncidents() {
  const res = await axiosInstance.get('/api/v1/customer-support/incidents');
  return res.data;
}

export async function getIncidentDetail(incidentId) {
  const res = await axiosInstance.get(`/api/v1/customer-support/incidents/${incidentId}`);
  return res.data;
}

// ── 6. Guided Support Request & AI Pre-Analysis ───────────────────────

export async function analyzeSupportRequest(payload) {
  const res = await axiosInstance.post('/api/v1/customer-support/requests/analyze', payload);
  return res.data;
}

// ── 7. Notification & Support Communication Center ───────────────────

export async function listNotifications(filter = null) {
  const params = filter ? { filter } : {};
  const res = await axiosInstance.get('/api/v1/customer-support/notifications', { params });
  return res.data;
}

export async function markNotificationRead(notificationId) {
  const res = await axiosInstance.post(`/api/v1/customer-support/notifications/${notificationId}/read`);
  return res.data;
}

export async function markAllNotificationsRead() {
  const res = await axiosInstance.post('/api/v1/customer-support/notifications/read-all');
  return res.data;
}

export async function getNotificationPreferences() {
  const res = await axiosInstance.get('/api/v1/customer-support/notifications/preferences');
  return res.data;
}

export async function updateNotificationPreferences(payload) {
  const res = await axiosInstance.put('/api/v1/customer-support/notifications/preferences', payload);
  return res.data;
}

