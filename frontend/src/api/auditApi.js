/**
 * api/auditApi.js
 *
 * Audit Log (Admin only) — read-only.
 */

import axiosInstance from './axiosInstance';

export async function listAuditLogs({
  entityType, entityId, action, correlationId, occurredFrom, occurredTo, beforeId, limit = 50,
} = {}) {
  const res = await axiosInstance.get('/api/v1/audit-logs', {
    params: {
      entity_type: entityType || undefined,
      entity_id: entityId || undefined,
      action: action || undefined,
      correlation_id: correlationId || undefined,
      occurred_from: occurredFrom || undefined,
      occurred_to: occurredTo || undefined,
      before_id: beforeId || undefined,
      limit,
    },
  });
  return res.data;
}
