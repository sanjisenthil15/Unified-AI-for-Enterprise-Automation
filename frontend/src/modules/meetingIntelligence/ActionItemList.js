/**
 * modules/meetingIntelligence/ActionItemList.js
 *
 * AI-extracted action items, with manual assignment to a registered user
 * (PATCH /meetings/{id}/action-items/{itemId}/assign), plus — when the
 * meeting is linked to a project — a "Create sprint task" action that
 * turns the item into an assigned Sprint task
 * (POST /meetings/{id}/action-items/{itemId}/convert).
 */

import React, { useEffect, useState } from 'react';
import { listUsers } from '../../api/authApi';
import { assignActionItem, convertActionItem } from '../../api/meetingApi';
import { getTeamAttendance } from '../../api/attendanceApi';
import { listSprints } from '../../api/sprintsApi';
import { formatDate } from './helpers';

const ITEM_STATUS_BADGE = {
  pending: 'purple',
  in_progress: 'blue',
  completed: 'green',
  cancelled: 'red',
};

export default function ActionItemList({ meetingId, projectId, items = [], onAssigned }) {
  const [users, setUsers] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [projectMembers, setProjectMembers] = useState([]);
  const [projectSprints, setProjectSprints] = useState([]);
  const [convertingId, setConvertingId] = useState(null);
  const [convertForm, setConvertForm] = useState({ sprintId: '', assigneeId: '', dueDate: '' });

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) { setProjectMembers([]); setProjectSprints([]); return; }
    getTeamAttendance({ projectId: Number(projectId) }).then((entries) => setProjectMembers(entries.map((e) => e.employee))).catch(() => {});
    listSprints(Number(projectId)).then(setProjectSprints).catch(() => {});
  }, [projectId]);

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

  function startConvert(item) {
    setConvertingId(item.id);
    setConvertForm({
      sprintId: '',
      assigneeId: item.assigned_to_employee_id ? String(item.assigned_to_employee_id) : '',
      dueDate: item.due_date || '',
    });
  }

  async function handleConvert(itemId) {
    if (!convertForm.sprintId || !convertForm.assigneeId) {
      setError('Pick a sprint and an assignee first.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await convertActionItem(meetingId, itemId, {
        sprintId: Number(convertForm.sprintId),
        assigneeId: Number(convertForm.assigneeId),
        dueDate: convertForm.dueDate || undefined,
      });
      setConvertingId(null);
      await onAssigned?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create a sprint task from this item.');
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
                  {projectId && (
                    it.converted_sprint_task_id ? (
                      <span className="badge green">✓ In Sprint</span>
                    ) : convertingId !== it.id ? (
                      <button type="button" className="mi-btn mi-btn-ghost mi-btn-sm" onClick={() => startConvert(it)}>
                        Create sprint task
                      </button>
                    ) : null
                  )}
                </div>

                {convertingId === it.id && (
                  <div className="mi-action-convert">
                    <select value={convertForm.sprintId} disabled={saving}
                      onChange={(e) => setConvertForm((f) => ({ ...f, sprintId: e.target.value }))}>
                      <option value="">Sprint…</option>
                      {projectSprints.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                    <select value={convertForm.assigneeId} disabled={saving}
                      onChange={(e) => setConvertForm((f) => ({ ...f, assigneeId: e.target.value }))}>
                      <option value="">Who should do this?</option>
                      {projectMembers.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                    </select>
                    <input type="date" value={convertForm.dueDate} disabled={saving}
                      onChange={(e) => setConvertForm((f) => ({ ...f, dueDate: e.target.value }))} />
                    <button type="button" className="mi-btn mi-btn-primary mi-btn-sm" disabled={saving}
                      onClick={() => handleConvert(it.id)}>
                      {saving ? 'Creating…' : 'Create task'}
                    </button>
                    <button type="button" className="mi-btn mi-btn-ghost mi-btn-sm" onClick={() => setConvertingId(null)}>
                      Cancel
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
