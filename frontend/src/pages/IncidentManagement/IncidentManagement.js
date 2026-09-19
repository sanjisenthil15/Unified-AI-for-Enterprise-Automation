/**
 * pages/IncidentManagement/IncidentManagement.js
 *
 * Full live Incident Management dashboard.
 * Replaces the static demo page.
 *
 * Sections:
 *   1. Stats banner         — real DB counts
 *   2. Filters + list       — severity / status filters, search, sort
 *   3. Create incident form
 *   4. Detail / action panel — update, status, assign, resolve, close, AI triage
 *   5. Timeline panel       — full audit history
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  getIncidentStats, listIncidents, getIncident,
  createIncident, updateIncident, deleteIncident,
  updateIncidentStatus, assignIncident,
  resolveIncident, closeIncident,
  runAITriage, getLatestTriage, getTimeline,
} from '../../api/incidentApi';
import '../Recruitment/Recruitment.css';
import './IncidentManagement.css';

// ── helpers ──────────────────────────────────────────────────────────

function getUser() {
  try { return JSON.parse(localStorage.getItem('user')) || {}; }
  catch { return {}; }
}

function fmt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });
}

const SEV_BADGE   = { low: 'green', medium: 'blue', high: 'amber', critical: 'red' };
const SEV_LABEL   = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' };
const STAT_BADGE  = { open: 'blue', investigating: 'amber', resolved: 'green', closed: 'purple' };
const STAT_LABEL  = { open: 'Open', investigating: 'Investigating', resolved: 'Resolved', closed: 'Closed' };

const WRITE_ROLES  = ['admin', 'manager', 'it_engineer'];
const ASSIGN_ROLES = ['admin', 'manager'];

function canWrite(user) { return WRITE_ROLES.includes(user?.role?.name?.toLowerCase()); }
function canAssign(user){ return ASSIGN_ROLES.includes(user?.role?.name?.toLowerCase()); }

// ── component ────────────────────────────────────────────────────────

export default function IncidentManagement() {
  const user = getUser();

  // stats
  const [stats, setStats] = useState(null);

  // list
  const [incidents,    setIncidents]    = useState([]);
  const [loading,      setLoading]      = useState(false);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSev,    setFilterSev]    = useState('');
  const [search,       setSearch]       = useState('');

  // create form
  const [showCreate, setShowCreate] = useState(false);
  const [creating,   setCreating]   = useState(false);
  const [createMsg,  setCreateMsg]  = useState(null);
  const [form, setForm] = useState({
    title: '', description: '', severity: 'medium', affected_system: '',
  });

  // detail panel
  const [selected,       setSelected]       = useState(null);   // full incident
  const [detailLoading,  setDetailLoading]  = useState(false);

  // timeline
  const [timeline,     setTimeline]    = useState([]);
  const [showTimeline, setShowTimeline] = useState(false);

  // triage
  const [triage,       setTriage]      = useState(null);
  const [triaging,     setTriaging]    = useState(false);
  const [triageMsg,    setTriageMsg]   = useState(null);

  // action modals
  const [actionModal,  setActionModal] = useState(null); // 'status'|'assign'|'resolve'|'update'
  const [actionBusy,   setActionBusy]  = useState(false);
  const [actionMsg,    setActionMsg]   = useState(null);
  const [actionData,   setActionData]  = useState({});

  // ── load ──────────────────────────────────────────────────────────

  const loadStats = useCallback(() => {
    getIncidentStats().then(setStats).catch(() => {});
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterStatus) params.status   = filterStatus;
      if (filterSev)    params.severity = filterSev;
      if (search)       params.search   = search;
      const data = await listIncidents(params);
      setIncidents(data);
    } catch { setIncidents([]); }
    finally { setLoading(false); }
  }, [filterStatus, filterSev, search]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { loadList();  }, [loadList]);

  // ── open detail ───────────────────────────────────────────────────

  async function openDetail(inc) {
    setDetailLoading(true);
    setSelected(null);
    setTriage(null);
    setTimeline([]);
    setShowTimeline(false);
    setTriageMsg(null);
    setActionMsg(null);
    try {
      const full = await getIncident(inc.id);
      setSelected(full);
      // Try loading existing triage silently
      getLatestTriage(inc.id).then(setTriage).catch(() => {});
    } catch { setSelected(inc); }
    finally { setDetailLoading(false); }
    setTimeout(() => document.getElementById('inc-detail')?.scrollIntoView({ behavior: 'smooth' }), 80);
  }

  // ── create ────────────────────────────────────────────────────────

  async function handleCreate(e) {
    e.preventDefault();
    if (!form.title.trim() || !form.description.trim()) {
      setCreateMsg({ type: 'error', text: 'Title and description are required.' });
      return;
    }
    setCreating(true);
    setCreateMsg(null);
    try {
      await createIncident({
        title:           form.title.trim(),
        description:     form.description.trim(),
        severity:        form.severity,
        affected_system: form.affected_system.trim() || undefined,
      });
      setForm({ title: '', description: '', severity: 'medium', affected_system: '' });
      setShowCreate(false);
      setCreateMsg({ type: 'success', text: 'Incident created.' });
      loadList();
      loadStats();
    } catch (err) {
      setCreateMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to create.' });
    } finally { setCreating(false); }
  }

  // ── action helpers ────────────────────────────────────────────────

  async function handleAction() {
    if (!selected) return;
    setActionBusy(true);
    setActionMsg(null);
    try {
      let updated;
      if (actionModal === 'status') {
        updated = await updateIncidentStatus(selected.id, actionData.status, actionData.notes);
      } else if (actionModal === 'assign') {
        const uid = parseInt(actionData.userId, 10);
        if (!uid) { setActionMsg({ type: 'error', text: 'Enter a valid user ID.' }); setActionBusy(false); return; }
        updated = await assignIncident(selected.id, uid, actionData.notes);
      } else if (actionModal === 'resolve') {
        if (!actionData.rootCause?.trim()) { setActionMsg({ type: 'error', text: 'Root cause is required.' }); setActionBusy(false); return; }
        updated = await resolveIncident(selected.id, actionData.rootCause, actionData.notes);
      } else if (actionModal === 'update') {
        updated = await updateIncident(selected.id, {
          title:           actionData.title,
          description:     actionData.description,
          severity:        actionData.severity,
          affected_system: actionData.affected_system,
        });
      }
      setSelected(updated);
      setIncidents(prev => prev.map(i => i.id === updated.id ? { ...i, ...updated } : i));
      setActionModal(null);
      loadStats();
    } catch (err) {
      setActionMsg({ type: 'error', text: err.response?.data?.detail || 'Action failed.' });
    } finally { setActionBusy(false); }
  }

  async function handleClose() {
    if (!selected) return;
    if (!window.confirm(`Close incident #${selected.id}?`)) return;
    try {
      const updated = await closeIncident(selected.id);
      setSelected(updated);
      setIncidents(prev => prev.map(i => i.id === updated.id ? { ...i, ...updated } : i));
      loadStats();
    } catch (err) {
      alert(err.response?.data?.detail || 'Close failed.');
    }
  }

  async function handleDelete() {
    if (!selected) return;
    if (!window.confirm(`Permanently delete incident #${selected.id}? This cannot be undone.`)) return;
    try {
      await deleteIncident(selected.id);
      setIncidents(prev => prev.filter(i => i.id !== selected.id));
      setSelected(null);
      loadStats();
    } catch (err) {
      alert(err.response?.data?.detail || 'Delete failed.');
    }
  }

  async function handleTriage() {
    if (!selected) return;
    setTriaging(true);
    setTriageMsg({ type: 'info', text: 'Running Gemini AI triage...' });
    try {
      const result = await runAITriage(selected.id);
      setTriage(result);
      setTriageMsg({ type: 'success', text: 'AI triage complete.' });
    } catch (err) {
      setTriageMsg({ type: 'error', text: err.response?.data?.detail || 'AI triage failed.' });
    } finally { setTriaging(false); }
  }

  async function handleLoadTimeline() {
    if (!selected) return;
    try {
      const entries = await getTimeline(selected.id);
      setTimeline(entries);
      setShowTimeline(true);
    } catch { setTimeline([]); }
  }

  // ── open action modal helpers ─────────────────────────────────────

  function openStatusModal() {
    setActionData({ status: selected?.status || 'open', notes: '' });
    setActionMsg(null);
    setActionModal('status');
  }
  function openAssignModal() {
    setActionData({ userId: selected?.assigned_to || '', notes: '' });
    setActionMsg(null);
    setActionModal('assign');
  }
  function openResolveModal() {
    setActionData({ rootCause: selected?.root_cause || '', notes: '' });
    setActionMsg(null);
    setActionModal('resolve');
  }
  function openUpdateModal() {
    setActionData({
      title:           selected?.title || '',
      description:     selected?.description || '',
      severity:        selected?.severity || 'medium',
      affected_system: selected?.affected_system || '',
    });
    setActionMsg(null);
    setActionModal('update');
  }

  // ── render ────────────────────────────────────────────────────────

  return (
    <div className="module-page inc-page">

      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon red" aria-hidden="true">🚨</div>
        <div>
          <h1>Incident Management</h1>
          <p>Log, triage, and resolve incidents. AI suggests severity and owner automatically.</p>
        </div>
      </div>

      {/* ── Stats ─────────────────────────────────────────────────── */}
      {stats && (
        <div className="stat-row inc-stats-row">
          {[
            { label: 'Total',        val: stats.total,         color: '#2563eb' },
            { label: 'Open',         val: stats.open,          color: '#d97706' },
            { label: 'Investigating',val: stats.investigating, color: '#7c3aed' },
            { label: 'Resolved',     val: stats.resolved,      color: '#16a34a' },
            { label: 'Closed',       val: stats.closed,        color: '#64748b' },
            { label: 'Critical',     val: stats.severity_critical, color: '#dc2626' },
            { label: 'High',         val: stats.severity_high,     color: '#ea580c' },
          ].map(s => (
            <div key={s.label} className="stat-card">
              <div className="stat-value" style={{ color: s.color, fontSize: '1.6rem' }}>{s.val}</div>
              <div className="stat-label">{s.label}</div>
              {s.label === 'Resolved' && stats.avg_resolution_minutes != null && (
                <div className="stat-note">Avg {Math.round(stats.avg_resolution_minutes)} min</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Controls ──────────────────────────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.25rem' }}>
        <div className="inc-controls">
          {/* Filters */}
          <div className="filter-chips">
            {['', 'open', 'investigating', 'resolved', 'closed'].map(s => (
              <button key={s}
                className={`filter-chip${filterStatus === s ? ' active' : ''}`}
                onClick={() => setFilterStatus(s)}>
                {s ? STAT_LABEL[s] : 'All Status'}
              </button>
            ))}
          </div>
          <div className="filter-chips" style={{ marginTop: '0.5rem' }}>
            {['', 'critical', 'high', 'medium', 'low'].map(s => (
              <button key={s}
                className={`filter-chip${filterSev === s ? ' active' : ''}`}
                onClick={() => setFilterSev(s)}>
                {s ? SEV_LABEL[s] : 'All Severity'}
              </button>
            ))}
          </div>

          <div className="inc-search-row">
            <input
              className="field-input"
              style={{ flex: 1, minWidth: 200 }}
              placeholder="Search title or description..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {canWrite(user) && (
              <button className="btn-primary"
                onClick={() => { setShowCreate(v => !v); setCreateMsg(null); }}>
                {showCreate ? '✕ Cancel' : '+ New Incident'}
              </button>
            )}
          </div>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="inc-create-box">
            {createMsg && <div className={`alert ${createMsg.type}`}>{createMsg.text}</div>}
            <form onSubmit={handleCreate}>
              <div className="form-grid">
                <div className="field-group full-width">
                  <label>Title *</label>
                  <input className="field-input" value={form.title}
                    onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                    placeholder="Short summary of the incident" required />
                </div>
                <div className="field-group full-width">
                  <label>Description *</label>
                  <textarea className="field-input" rows={3} value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="Detailed description — what is failing, impact, when it started..."
                    style={{ resize: 'vertical' }} required />
                </div>
                <div className="field-group">
                  <label>Severity</label>
                  <select className="field-select" value={form.severity}
                    onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div className="field-group">
                  <label>Affected System</label>
                  <input className="field-input" value={form.affected_system}
                    onChange={e => setForm(f => ({ ...f, affected_system: e.target.value }))}
                    placeholder="e.g. Payment Service, Auth API" />
                </div>
              </div>
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem' }}>
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? 'Creating...' : '+ Create Incident'}
                </button>
                <button type="button" className="btn-secondary"
                  onClick={() => setShowCreate(false)}>Cancel</button>
              </div>
            </form>
          </div>
        )}
        {!showCreate && createMsg?.type === 'success' && (
          <div className="alert success" style={{ marginTop: '0.75rem' }}>{createMsg.text}</div>
        )}
      </div>

      {/* ── Incident Table ─────────────────────────────────────────── */}
      <div className="content-panel" style={{ marginBottom: '1.25rem' }}>
        <h2>
          Incidents
          {loading && <span style={{ fontSize: '0.8rem', fontWeight: 400, color: 'var(--text-muted)', marginLeft: '0.75rem' }}>Loading...</span>}
        </h2>
        {incidents.length === 0 && !loading ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            No incidents match the current filters.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" aria-label="Incident list">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Title</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Affected System</th>
                  <th>Reported</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map(inc => (
                  <tr key={inc.id}
                    style={{ cursor: 'pointer', background: selected?.id === inc.id ? '#eff6ff' : undefined }}
                    onClick={() => openDetail(inc)}>
                    <td><strong>INC-{String(inc.id).padStart(4, '0')}</strong></td>
                    <td style={{ maxWidth: 260, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {inc.title}
                    </td>
                    <td>
                      <span className={`badge ${SEV_BADGE[inc.severity] || 'blue'}`}>
                        {SEV_LABEL[inc.severity] || inc.severity}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${STAT_BADGE[inc.status] || 'blue'}`}>
                        {STAT_LABEL[inc.status] || inc.status}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      {inc.affected_system || '—'}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {fmt(inc.created_at)}
                    </td>
                    <td>
                      <button className="btn-link" onClick={e => { e.stopPropagation(); openDetail(inc); }}>
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Detail Panel ──────────────────────────────────────────── */}
      {(detailLoading || selected) && (
        <div className="content-panel" id="inc-detail" style={{ marginBottom: '1.25rem' }}>
          {detailLoading && <p style={{ color: 'var(--text-muted)' }}>Loading incident...</p>}
          {!detailLoading && selected && (() => {
            const canW = canWrite(user);
            const canA = canAssign(user);
            const isResolved = selected.status === 'resolved';
            const isClosed   = selected.status === 'closed';
            return (
              <>
                {/* Header row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                  <div>
                    <h2 style={{ borderBottom: 'none', marginBottom: '0.25rem' }}>
                      INC-{String(selected.id).padStart(4, '0')} — {selected.title}
                    </h2>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      <span className={`badge ${SEV_BADGE[selected.severity] || 'blue'}`}>
                        {SEV_LABEL[selected.severity] || selected.severity}
                      </span>
                      <span className={`badge ${STAT_BADGE[selected.status] || 'blue'}`}>
                        {STAT_LABEL[selected.status] || selected.status}
                      </span>
                    </div>
                  </div>
                  <button className="btn-link" onClick={() => setSelected(null)}>✕ Close</button>
                </div>

                {/* Meta grid */}
                <div className="detail-meta-grid" style={{ marginBottom: '1rem' }}>
                  <div>
                    <span className="dmeta-label">Affected System</span>
                    {selected.affected_system || '—'}
                  </div>
                  <div>
                    <span className="dmeta-label">Reported By</span>
                    {selected.reporter?.full_name || `User #${selected.reported_by}`}
                  </div>
                  <div>
                    <span className="dmeta-label">Assigned To</span>
                    {selected.assignee?.full_name || (selected.assigned_to ? `User #${selected.assigned_to}` : 'Unassigned')}
                  </div>
                  <div>
                    <span className="dmeta-label">Reported At</span>
                    {fmt(selected.created_at)}
                  </div>
                  <div>
                    <span className="dmeta-label">Last Updated</span>
                    {fmt(selected.updated_at)}
                  </div>
                  <div>
                    <span className="dmeta-label">Resolved At</span>
                    {fmt(selected.resolved_at)}
                  </div>
                </div>

                {/* Description */}
                <div style={{ marginBottom: '1rem' }}>
                  <div className="detail-ai-label" style={{ marginBottom: '0.3rem' }}>Description</div>
                  <div style={{ fontSize: '0.9rem', lineHeight: 1.65, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                    {selected.description}
                  </div>
                </div>

                {/* Root cause */}
                {selected.root_cause && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div className="detail-ai-label" style={{ marginBottom: '0.3rem' }}>Root Cause</div>
                    <div style={{ fontSize: '0.9rem', lineHeight: 1.65, color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                      {selected.root_cause}
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                {canW && (
                  <div className="inc-action-bar">
                    <button className="btn-secondary" onClick={openUpdateModal}>Edit</button>
                    <button className="btn-secondary" onClick={openStatusModal}>Change Status</button>
                    {canA && <button className="btn-secondary" onClick={openAssignModal}>Assign</button>}
                    {!isResolved && !isClosed && (
                      <button className="btn-secondary" onClick={openResolveModal}>Resolve</button>
                    )}
                    {!isClosed && (
                      <button className="btn-secondary" onClick={handleClose}>Close</button>
                    )}
                    <button className="btn-secondary danger-btn" onClick={handleDelete}>Delete</button>
                  </div>
                )}

                {/* AI Triage */}
                <div className="inc-triage-section">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>🤖 AI Triage</span>
                    {canW && (
                      <button className="btn-primary" style={{ padding: '0.4rem 1rem', fontSize: '0.82rem' }}
                        onClick={handleTriage} disabled={triaging}>
                        {triaging ? 'Analyzing...' : 'Run AI Triage'}
                      </button>
                    )}
                  </div>

                  {triageMsg && <div className={`alert ${triageMsg.type}`} style={{ marginBottom: '0.75rem' }}>{triageMsg.text}</div>}

                  {triage && (
                    <div className="detail-ai-grid">
                      <div className="detail-ai-cell">
                        <div className="detail-ai-label">Suggested Severity</div>
                        <span className={`badge ${SEV_BADGE[triage.suggested_severity] || 'blue'}`}>
                          {SEV_LABEL[triage.suggested_severity] || triage.suggested_severity}
                        </span>
                      </div>
                      <div className="detail-ai-cell">
                        <div className="detail-ai-label">Suggested Owner</div>
                        <div className="detail-ai-val">{triage.suggested_owner || '—'}</div>
                      </div>
                      <div className="detail-ai-cell">
                        <div className="detail-ai-label">Confidence</div>
                        <div className="detail-ai-val">
                          {triage.confidence != null ? `${parseFloat(triage.confidence).toFixed(1)}%` : '—'}
                        </div>
                      </div>
                      <div className="detail-ai-cell">
                        <div className="detail-ai-label">AI Model</div>
                        <div className="detail-ai-val" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {triage.ai_model}
                        </div>
                      </div>
                      <div className="detail-ai-cell" style={{ gridColumn: '1/-1' }}>
                        <div className="detail-ai-label">Reasoning</div>
                        <div className="detail-ai-val">{triage.reasoning}</div>
                      </div>
                    </div>
                  )}
                  {!triage && !triageMsg && (
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      No AI triage yet. Click "Run AI Triage" to analyze this incident with Gemini.
                    </p>
                  )}
                </div>

                {/* Timeline */}
                <div style={{ marginTop: '1.25rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>📋 Timeline / Audit</span>
                    <button className="btn-secondary" style={{ padding: '0.35rem 0.9rem', fontSize: '0.82rem' }}
                      onClick={handleLoadTimeline}>
                      {showTimeline ? 'Refresh' : 'Load Timeline'}
                    </button>
                    {showTimeline && (
                      <button className="btn-link" onClick={() => setShowTimeline(false)}>Hide</button>
                    )}
                  </div>
                  {showTimeline && (
                    <div className="inc-timeline">
                      {timeline.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No timeline entries.</p>
                      ) : (
                        timeline.map(entry => (
                          <div key={entry.id} className="inc-timeline-entry">
                            <div className="inc-timeline-dot" />
                            <div className="inc-timeline-body">
                              <div className="inc-timeline-action">{entry.action.replace(/_/g, ' ')}</div>
                              {entry.notes && (
                                <div className="inc-timeline-notes">{entry.notes}</div>
                              )}
                              <div className="inc-timeline-meta">
                                {entry.actor ? entry.actor.full_name : 'AI'}
                                {' · '}
                                {fmt(entry.created_at)}
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* ── Action Modals ──────────────────────────────────────────── */}
      {actionModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>
                {actionModal === 'status'  && 'Change Status'}
                {actionModal === 'assign'  && 'Assign Incident'}
                {actionModal === 'resolve' && 'Resolve Incident'}
                {actionModal === 'update'  && 'Edit Incident'}
              </h3>
              <button className="btn-link" onClick={() => setActionModal(null)}>✕</button>
            </div>

            {actionMsg && <div className={`alert ${actionMsg.type}`}>{actionMsg.text}</div>}

            {/* Status change */}
            {actionModal === 'status' && (
              <div>
                <div className="field-group" style={{ marginBottom: '1rem' }}>
                  <label>New Status</label>
                  <select className="field-select"
                    value={actionData.status}
                    onChange={e => setActionData(d => ({ ...d, status: e.target.value }))}>
                    <option value="open">Open</option>
                    <option value="investigating">Investigating</option>
                    <option value="resolved">Resolved</option>
                    <option value="closed">Closed</option>
                  </select>
                </div>
                <div className="field-group" style={{ marginBottom: '1rem' }}>
                  <label>Notes (optional)</label>
                  <textarea className="field-input" rows={2} value={actionData.notes || ''}
                    onChange={e => setActionData(d => ({ ...d, notes: e.target.value }))}
                    style={{ resize: 'vertical' }} />
                </div>
              </div>
            )}

            {/* Assign */}
            {actionModal === 'assign' && (
              <div>
                <div className="field-group" style={{ marginBottom: '1rem' }}>
                  <label>User ID to assign</label>
                  <input className="field-input" type="number" min="1"
                    value={actionData.userId || ''}
                    onChange={e => setActionData(d => ({ ...d, userId: e.target.value }))}
                    placeholder="Enter user ID" />
                </div>
                <div className="field-group" style={{ marginBottom: '1rem' }}>
                  <label>Notes (optional)</label>
                  <textarea className="field-input" rows={2} value={actionData.notes || ''}
                    onChange={e => setActionData(d => ({ ...d, notes: e.target.value }))}
                    style={{ resize: 'vertical' }} />
                </div>
              </div>
            )}

            {/* Resolve */}
            {actionModal === 'resolve' && (
              <div>
                <div className="field-group" style={{ marginBottom: '1rem' }}>
                  <label>Root Cause *</label>
                  <textarea className="field-input" rows={4}
                    value={actionData.rootCause || ''}
                    onChange={e => setActionData(d => ({ ...d, rootCause: e.target.value }))}
                    placeholder="Describe what caused this incident and how it was fixed..."
                    style={{ resize: 'vertical' }} />
                </div>
                <div className="field-group" style={{ marginBottom: '1rem' }}>
                  <label>Notes (optional)</label>
                  <textarea className="field-input" rows={2} value={actionData.notes || ''}
                    onChange={e => setActionData(d => ({ ...d, notes: e.target.value }))}
                    style={{ resize: 'vertical' }} />
                </div>
              </div>
            )}

            {/* Update */}
            {actionModal === 'update' && (
              <div className="form-grid">
                <div className="field-group full-width">
                  <label>Title</label>
                  <input className="field-input" value={actionData.title || ''}
                    onChange={e => setActionData(d => ({ ...d, title: e.target.value }))} />
                </div>
                <div className="field-group full-width">
                  <label>Description</label>
                  <textarea className="field-input" rows={4}
                    value={actionData.description || ''}
                    onChange={e => setActionData(d => ({ ...d, description: e.target.value }))}
                    style={{ resize: 'vertical' }} />
                </div>
                <div className="field-group">
                  <label>Severity</label>
                  <select className="field-select"
                    value={actionData.severity || 'medium'}
                    onChange={e => setActionData(d => ({ ...d, severity: e.target.value }))}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
                <div className="field-group">
                  <label>Affected System</label>
                  <input className="field-input"
                    value={actionData.affected_system || ''}
                    onChange={e => setActionData(d => ({ ...d, affected_system: e.target.value }))} />
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.25rem' }}>
              <button className="btn-primary" onClick={handleAction} disabled={actionBusy}>
                {actionBusy ? 'Saving...' : 'Save'}
              </button>
              <button className="btn-secondary" onClick={() => setActionModal(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
