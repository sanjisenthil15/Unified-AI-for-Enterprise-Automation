/**
 * modules/meetingIntelligence/ActionItemList.js
 *
 * AI-extracted action items, with manual assignment to a registered user
 * (PATCH /meetings/{id}/action-items/{itemId}/assign).
 */

import React, { useEffect, useState } from 'react';
import { listUsers } from '../../api/authApi';
import { assignActionItem } from '../../api/meetingApi';
import { formatDate } from './helpers';

const ITEM_STATUS_BADGE = {
  pending: 'purple',
  in_progress: 'blue',
  completed: 'green',
  cancelled: 'red',
};

export default function ActionItemList({ meetingId, items = [], onAssigned }) {
  const [users, setUsers] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
  }, []);

  async function handleAssign(itemId, userId) {
    setSaving(true);
    setError('');
    try {
      await assignActionItem(meetingId, itemId, userId ? Number(userId) : null);
      setEditingId(null);
      await onAssigned?.();
    } catch {
      setError('Could not update the assignment. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="content-panel mi-panel">
      <h2>Action Items <span className="mi-count">{items.length}</span></h2>
      {error && <div className="mi-error" role="alert">{error}</div>}

      {items.length === 0 ? (
        <p className="mi-muted">No action items were extracted from this meeting.</p>
      ) : (
        <ul className="mi-action-items">
          {items.map((it) => {
            const badge = ITEM_STATUS_BADGE[it.status] || 'purple';
            const assignedUser = users.find((u) => u.id === it.assigned_to_user_id);
            const assignee =
              assignedUser
                ? assignedUser.full_name
                : it.assigned_to_user_id
                ? `User #${it.assigned_to_user_id}`
                : it.assigned_to_employee_id
                ? `Employee #${it.assigned_to_employee_id}`
                : it.assignee_name_raw
                ? `${it.assignee_name_raw} (from transcript)`
                : 'Unassigned';

            return (
              <li key={it.id} className="mi-action-item">
                <div className="mi-action-main">
                  <span className={`badge ${badge}`}>{it.status.replace('_', ' ')}</span>
                  <span className="mi-action-desc">{it.description}</span>
                </div>
                <div className="mi-action-meta">
                  {editingId === it.id ? (
                    <select
                      autoFocus
                      disabled={saving}
                      value={it.assigned_to_user_id || ''}
                      onChange={(e) => handleAssign(it.id, e.target.value)}
                      onBlur={() => setEditingId(null)}
                    >
                      <option value="">Unassigned</option>
                      {users.map((u) => (
                        <option key={u.id} value={u.id}>{u.full_name}</option>
                      ))}
                    </select>
                  ) : (
                    <span>👤 {assignee}</span>
                  )}
                  {it.due_date && <span>📅 {formatDate(it.due_date)}</span>}
                  {it.priority && <span>⚑ {it.priority}</span>}
                  {it.ai_confidence != null && (
                    <span title="AI confidence this was an action item">
                      🤖 {Math.round(it.ai_confidence * 100)}%
                    </span>
                  )}
                  {editingId !== it.id && (
                    <button
                      type="button"
                      className="mi-btn mi-btn-ghost mi-btn-sm"
                      onClick={() => setEditingId(it.id)}
                    >
                      Assign person
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
