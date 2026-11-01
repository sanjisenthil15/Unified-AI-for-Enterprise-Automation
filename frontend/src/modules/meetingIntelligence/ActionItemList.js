/**
 * modules/meetingIntelligence/ActionItemList.js
 *
 * AI-extracted action items with formal approval review lifecycle (Submodule 4.2):
 *   proposed -> confirmed -> converted (or proposed -> rejected)
 *
 * Authorized reviewers (Admin, assigned Manager, assigned Team Lead):
 *   - Confirm: Assigns project employee, sets mandatory due date, optional final description
 *   - Reject: Sets terminal rejected state with mandatory non-empty reason
 *   - Convert: Selects sprint and converts to sprint task atomically
 *
 * Team members / employees have read-only visibility into review states and attribution.
 */

import React, { useEffect, useState } from 'react';
import { listUsers } from '../../api/authApi';
import { listEmployees } from '../../api/employeeApi';
import {
  assignActionItem,
  confirmActionItem,
  convertActionItem,
  rejectActionItem,
} from '../../api/meetingApi';
import { listSprints } from '../../api/sprintsApi';
import { formatDate } from './helpers';

const REVIEW_STATUS_BADGE = {
  proposed: 'amber',
  confirmed: 'blue',
  rejected: 'red',
  converted: 'green',
};

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('user')) || {};
  } catch {
    return {};
  }
}

export default function ActionItemList({ meetingId, projectId, items = [], onAssigned }) {
  const [users, setUsers] = useState([]);
  const [projectMembers, setProjectMembers] = useState([]);
  const [projectSprints, setProjectSprints] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Review states
  const [confirmingId, setConfirmingId] = useState(null);
  const [confirmForm, setConfirmForm] = useState({ assigneeId: '', dueDate: '', finalDescription: '' });

  const [rejectingId, setRejectingId] = useState(null);
  const [rejectReason, setRejectReason] = useState('');

  const [convertingId, setConvertingId] = useState(null);
  const [convertSprintId, setConvertSprintId] = useState('');

  const currentUser = getCurrentUser();
  const roleName = currentUser.role?.name?.toLowerCase() || '';
  const canReview = ['admin', 'manager', 'team_lead'].includes(roleName);

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) {
      setProjectMembers([]);
      setProjectSprints([]);
      return;
    }
    listEmployees({ status: 'active' })
      .then((emps) => {
        const members = emps.filter((e) => e.project?.id === Number(projectId));
        setProjectMembers(members);
      })
      .catch(() => {});

    listSprints(Number(projectId))
      .then(setProjectSprints)
      .catch(() => {});
  }, [projectId]);

  function startConfirm(it) {
    setError('');
    setRejectingId(null);
    setConvertingId(null);
    setConfirmingId(it.id);
    setConfirmForm({
      assigneeId: it.assigned_to_employee_id ? String(it.assigned_to_employee_id) : '',
      dueDate: it.due_date || '',
      finalDescription: it.final_description || it.description || '',
    });
  }

  async function handleConfirmSubmit(itemId) {
    if (!confirmForm.assigneeId) {
      setError('An assigned employee is required to confirm an action item.');
      return;
    }
    if (!confirmForm.dueDate) {
      setError('A due date deadline is required to confirm an action item.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await confirmActionItem(meetingId, itemId, {
        assigneeId: Number(confirmForm.assigneeId),
        dueDate: confirmForm.dueDate,
        finalDescription: confirmForm.finalDescription?.trim() || null,
      });
      setConfirmingId(null);
      await onAssigned?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not confirm this action item.');
    } finally {
      setSaving(false);
    }
  }

  function startReject(it) {
    setError('');
    setConfirmingId(null);
    setConvertingId(null);
    setRejectingId(it.id);
    setRejectReason('');
  }

  async function handleRejectSubmit(itemId) {
    if (!rejectReason.trim()) {
      setError('A non-empty rejection reason is required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await rejectActionItem(meetingId, itemId, {
        rejectionReason: rejectReason.trim(),
      });
      setRejectingId(null);
      await onAssigned?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not reject this action item.');
    } finally {
      setSaving(false);
    }
  }

  function startConvert(it) {
    setError('');
    setConfirmingId(null);
    setRejectingId(null);
    setConvertingId(it.id);
    setConvertSprintId('');
  }

  async function handleConvertSubmit(itemId) {
    if (!convertSprintId) {
      setError('Select a destination sprint to convert this item into a task.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await convertActionItem(meetingId, itemId, {
        sprintId: Number(convertSprintId),
      });
      setConvertingId(null);
      await onAssigned?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not convert action item to sprint task.');
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
            const reviewStatus = it.review_status || 'proposed';
            const reviewBadgeColor = REVIEW_STATUS_BADGE[reviewStatus] || 'purple';

            // Resolve assignee display
            const assignedMember = projectMembers.find((m) => m.id === it.assigned_to_employee_id);
            const assignedUser = users.find((u) => u.id === it.assigned_to_user_id);
            const assigneeName = assignedMember?.user?.full_name
              || assignedUser?.full_name
              || (it.assigned_to_employee_id ? `Employee #${it.assigned_to_employee_id}` : null)
              || (it.assigned_to_user_id ? `User #${it.assigned_to_user_id}` : null)
              || (it.assignee_name_raw ? `${it.assignee_name_raw} (AI detected)` : 'Unassigned');

            const hasEditedDescription = Boolean(it.final_description && it.final_description !== it.description);

            return (
              <li key={it.id} className="mi-action-item">
                <div className="mi-action-main">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                    <span className={`badge ${reviewBadgeColor}`}>
                      {reviewStatus.toUpperCase()}
                    </span>
                    {it.is_legacy_conversion && (
                      <span className="badge purple" title="Converted prior to Submodule 4.2 review workflow">
                        Legacy Conversion
                      </span>
                    )}
                    {it.converted_sprint_task_id && (
                      <span className="badge green">
                        ✓ In Sprint (Task #{it.converted_sprint_task_id})
                      </span>
                    )}
                  </div>

                  <div className="mi-action-desc">
                    {hasEditedDescription ? (
                      <div>
                        <strong>{it.final_description}</strong>
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
                          <em>Original AI: {it.description}</em>
                        </div>
                      </div>
                    ) : (
                      <strong>{it.description}</strong>
                    )}
                  </div>
                </div>

                <div className="mi-action-meta" style={{ flexWrap: 'wrap', gap: '0.6rem', marginTop: '0.5rem' }}>
                  <span>👤 {assigneeName}</span>
                  {it.due_date && <span>📅 Due: {formatDate(it.due_date)}</span>}
                  {it.priority && <span>⚑ {it.priority}</span>}
                  {it.ai_confidence != null && (
                    <span title="AI confidence extraction score">
                      🤖 {Math.round(it.ai_confidence * 100)}%
                    </span>
                  )}
                  {it.reviewed_by_name && (
                    <span>
                      ✍️ Reviewed by: <strong>{it.reviewed_by_name}</strong>
                      {it.reviewed_at && ` (${formatDate(it.reviewed_at)})`}
                    </span>
                  )}
                  {it.rejection_reason && (
                    <span style={{ color: 'var(--error, #e53935)' }}>
                      ✕ Reason: <em>{it.rejection_reason}</em>
                    </span>
                  )}
                </div>

                {/* Review Controls for Authorized Users (Admin, Manager, Team Lead) */}
                {canReview && projectId && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {reviewStatus === 'proposed' && confirmingId !== it.id && rejectingId !== it.id && (
                      <>
                        <button
                          type="button"
                          className="mi-btn mi-btn-primary mi-btn-sm"
                          onClick={() => startConfirm(it)}
                        >
                          ✓ Confirm & Assign
                        </button>
                        <button
                          type="button"
                          className="mi-btn mi-btn-danger mi-btn-sm"
                          onClick={() => startReject(it)}
                        >
                          ✕ Reject
                        </button>
                      </>
                    )}

                    {reviewStatus === 'confirmed' && !it.converted_sprint_task_id && convertingId !== it.id && (
                      <button
                        type="button"
                        className="mi-btn mi-btn-primary mi-btn-sm"
                        onClick={() => startConvert(it)}
                      >
                        🚀 Convert to Sprint Task
                      </button>
                    )}
                  </div>
                )}

                {/* Confirm Inline Form */}
                {confirmingId === it.id && (
                  <div className="mi-action-convert" style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'var(--surface-sunken, #f8f7fc)', borderRadius: '6px' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>Confirm & Approve Action Item</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>
                          Assign Project Member *
                        </label>
                        <select
                          className="field-select"
                          value={confirmForm.assigneeId}
                          disabled={saving}
                          onChange={(e) => setConfirmForm((f) => ({ ...f, assigneeId: e.target.value }))}
                          style={{ width: '100%' }}
                        >
                          <option value="">Select project member…</option>
                          {projectMembers.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.user?.full_name} ({m.job_title})
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>
                          Due Date *
                        </label>
                        <input
                          type="date"
                          className="field-input"
                          value={confirmForm.dueDate}
                          disabled={saving}
                          onChange={(e) => setConfirmForm((f) => ({ ...f, dueDate: e.target.value }))}
                          style={{ width: '100%' }}
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>
                          Approved Description (Optional edit)
                        </label>
                        <textarea
                          className="field-input"
                          rows={2}
                          value={confirmForm.finalDescription}
                          disabled={saving}
                          onChange={(e) => setConfirmForm((f) => ({ ...f, finalDescription: e.target.value }))}
                          style={{ width: '100%' }}
                        />
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                        <button
                          type="button"
                          className="mi-btn mi-btn-primary mi-btn-sm"
                          disabled={saving}
                          onClick={() => handleConfirmSubmit(it.id)}
                        >
                          {saving ? 'Approving…' : 'Approve & Confirm'}
                        </button>
                        <button
                          type="button"
                          className="mi-btn mi-btn-ghost mi-btn-sm"
                          disabled={saving}
                          onClick={() => setConfirmingId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Reject Inline Form */}
                {rejectingId === it.id && (
                  <div className="mi-action-convert" style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'var(--surface-sunken, #f8f7fc)', borderRadius: '6px' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: 'var(--error, #e53935)' }}>
                      Reject Action Item
                    </h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>
                          Rejection Reason *
                        </label>
                        <textarea
                          className="field-input"
                          rows={2}
                          placeholder="Provide the reason for rejecting this proposed action item…"
                          value={rejectReason}
                          disabled={saving}
                          onChange={(e) => setRejectReason(e.target.value)}
                          style={{ width: '100%' }}
                        />
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                        <button
                          type="button"
                          className="mi-btn mi-btn-danger mi-btn-sm"
                          disabled={saving || !rejectReason.trim()}
                          onClick={() => handleRejectSubmit(it.id)}
                        >
                          {saving ? 'Rejecting…' : 'Confirm Rejection'}
                        </button>
                        <button
                          type="button"
                          className="mi-btn mi-btn-ghost mi-btn-sm"
                          disabled={saving}
                          onClick={() => setRejectingId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Convert to Sprint Task Form */}
                {convertingId === it.id && (
                  <div className="mi-action-convert" style={{ marginTop: '0.75rem', padding: '0.75rem', background: 'var(--surface-sunken, #f8f7fc)', borderRadius: '6px' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>Convert to Sprint Task</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>
                          Target Sprint *
                        </label>
                        <select
                          className="field-select"
                          value={convertSprintId}
                          disabled={saving}
                          onChange={(e) => setConvertSprintId(e.target.value)}
                          style={{ width: '100%' }}
                        >
                          <option value="">Select sprint…</option>
                          {projectSprints.map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.name} ({s.status})
                            </option>
                          ))}
                        </select>
                      </div>

                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
                        <button
                          type="button"
                          className="mi-btn mi-btn-primary mi-btn-sm"
                          disabled={saving || !convertSprintId}
                          onClick={() => handleConvertSubmit(it.id)}
                        >
                          {saving ? 'Converting…' : 'Create Sprint Task'}
                        </button>
                        <button
                          type="button"
                          className="mi-btn mi-btn-ghost mi-btn-sm"
                          disabled={saving}
                          onClick={() => setConvertingId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
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
