/**
 * pages/Projects/Projects.js
 *
 * Dedicated project portfolio page, open to every signed-in user. What
 * each person sees is scoped by the backend (GET /employee-management/projects):
 *   - Admin / HR Manager: every project; create, edit, change status,
 *     assign the Manager and Team Lead, delete empty projects.
 *   - Manager: only the projects they're assigned to; may edit metadata
 *     and move them through the lifecycle.
 *   - Team lead / employee: their own project, read-only.
 * The buttons shown here only mirror those rules — the API enforces them.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  assignProjectManager, assignTeamLead, createProject, deleteProject, listEmployees,
  listProjects, updateProject, updateProjectStatus,
} from '../../api/employeeApi';
import Avatar from '../../components/common/Avatar';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import {
  PROJECT_ADMIN_ROLES, PROJECT_STATUSES, PROJECT_STATUS_BADGE, allowedNextStatuses,
  canEditProjectMetadata, canManageProject, projectStatusLabel,
} from '../../utils/projectLifecycle';
import { apiErrorText } from '../../utils/passwordPolicy';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './Projects.css';

// Roles allowed to read the employee directory (backend EMPLOYEE_VIEW_ROLES).
const DIRECTORY_ROLES = ['admin', 'hr_manager', 'manager'];

// Transitions that can't be undone get an explicit confirmation.
const CONFIRM_TRANSITION = {
  completed: 'Mark this project completed? Completed projects cannot be reopened.',
  cancelled: 'Cancel this project? Cancelled projects cannot be reopened.',
  archived: 'Archive this project? Archived projects become read-only.',
};

const EMPTY_CREATE = { name: '', description: '', startDate: '', deadline: '', status: 'planning' };

function currentUser() {
  try {
    return JSON.parse(localStorage.getItem('user')) || null;
  } catch {
    return null;
  }
}

function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString();
}

function editFormFrom(project) {
  return {
    name: project.name || '',
    description: project.description || '',
    startDate: project.start_date || '',
    deadline: project.deadline || '',
  };
}

export default function Projects() {
  const [me] = useState(currentUser);
  const authDisabled = process.env.REACT_APP_AUTH_DISABLED === 'true';
  const role = authDisabled ? 'admin' : (me?.role?.name?.toLowerCase() ?? '');
  const userId = me?.id ?? null;
  const isProjectAdmin = PROJECT_ADMIN_ROLES.includes(role);
  const canSeeDirectory = DIRECTORY_ROLES.includes(role);

  const [projects, setProjects] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedId, setSelectedId] = useState(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(EMPTY_CREATE);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [managerPick, setManagerPick] = useState('');
  const [leadPick, setLeadPick] = useState('');

  const load = useCallback(async () => {
    try {
      const [projs, emps] = await Promise.all([
        listProjects(),
        canSeeDirectory ? listEmployees().catch(() => []) : Promise.resolve([]),
      ]);
      setProjects(projs);
      setEmployees(emps);
      setError('');
    } catch (err) {
      setError(apiErrorText(err, 'Could not load projects. Check backend availability.'));
    } finally {
      setLoading(false);
    }
  }, [canSeeDirectory]);

  useEffect(() => { load(); }, [load]);

  const selected = projects.find((p) => p.id === selectedId) || null;

  // Reset per-project form state whenever a different project is opened.
  useEffect(() => {
    setEditing(false);
    setEditForm(null);
    setManagerPick('');
    setLeadPick('');
  }, [selectedId]);

  const counts = useMemo(() => {
    const c = { all: projects.length };
    PROJECT_STATUSES.forEach((s) => { c[s] = 0; });
    projects.forEach((p) => { c[p.status || 'planning'] = (c[p.status || 'planning'] || 0) + 1; });
    return c;
  }, [projects]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return projects.filter((p) => {
      if (statusFilter !== 'all' && (p.status || 'planning') !== statusFilter) return false;
      if (!q) return true;
      return [p.name, p.description, p.manager?.full_name, p.team_lead?.user?.full_name]
        .some((v) => (v || '').toLowerCase().includes(q));
    });
  }, [projects, search, statusFilter]);

  const activeManagers = useMemo(() => employees
    .filter((emp) => emp.user?.role?.name === 'manager' && emp.user?.is_active && emp.status === 'active')
    .map((emp) => emp.user), [employees]);

  const members = useMemo(() => (selected
    ? employees.filter((emp) => emp.project?.id === selected.id)
    : []), [employees, selected]);

  async function run(action, successText) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
      // Refresh first so the confirmation never sits next to stale data.
      await load();
      if (successText) setNotice(successText);
      return true;
    } catch (err) {
      setError(apiErrorText(err, 'That action could not be completed.'));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    const name = createForm.name.trim();
    if (name.length < 2) {
      setError('Project name must be at least 2 characters.');
      return;
    }
    if (createForm.startDate && createForm.deadline && createForm.deadline < createForm.startDate) {
      setError('The deadline must be on or after the start date.');
      return;
    }
    const ok = await run(() => createProject({
      name,
      description: createForm.description.trim() || null,
      startDate: createForm.startDate || null,
      deadline: createForm.deadline || null,
      status: createForm.status,
    }), `Project "${name}" created.`);
    if (ok) {
      setCreateForm(EMPTY_CREATE);
      setShowCreate(false);
    }
  }

  async function handleSaveEdit(e) {
    e.preventDefault();
    if (!selected || !editForm) return;
    if (editForm.name.trim().length < 2) {
      setError('Project name must be at least 2 characters.');
      return;
    }
    if (editForm.startDate && editForm.deadline && editForm.deadline < editForm.startDate) {
      setError('The deadline must be on or after the start date.');
      return;
    }
    const ok = await run(() => updateProject(selected.id, {
      name: editForm.name.trim(),
      description: editForm.description.trim() || null,
      startDate: editForm.startDate || null,
      deadline: editForm.deadline || null,
    }), 'Project details saved.');
    if (ok) setEditing(false);
  }

  async function handleTransition(target) {
    if (!selected) return;
    // eslint-disable-next-line no-alert
    if (CONFIRM_TRANSITION[target] && !window.confirm(CONFIRM_TRANSITION[target])) return;
    await run(
      () => updateProjectStatus(selected.id, target),
      `Status changed to ${projectStatusLabel(target)}.`,
    );
  }

  async function handleAssignManager() {
    if (!selected || !managerPick) return;
    const ok = await run(() => assignProjectManager(selected.id, Number(managerPick)), 'Project manager assigned.');
    if (ok) setManagerPick('');
  }

  async function handleAssignLead() {
    if (!selected || !leadPick) return;
    const ok = await run(() => assignTeamLead(selected.id, Number(leadPick)), 'Team lead assigned.');
    if (ok) setLeadPick('');
  }

  async function handleDelete() {
    if (!selected) return;
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete "${selected.name}"? Only empty projects (no sprints, meetings or members) can be deleted.`)) return;
    const ok = await run(() => deleteProject(selected.id), `Project "${selected.name}" deleted.`);
    if (ok) setSelectedId(null);
  }

  const subtitle = isProjectAdmin
    ? 'Every project in the organisation — create, staff and move projects through their lifecycle.'
    : role === 'manager'
      ? 'The projects you manage — keep their details and lifecycle status up to date.'
      : 'The project you work on, its team and its timeline.';

  return (
    <div className="module-page projects-page">
      <div className="module-page-header">
        <div className="module-page-icon purple" aria-hidden="true">📁</div>
        <div>
          <h1>Projects</h1>
          <p>{subtitle}</p>
        </div>
        {isProjectAdmin && (
          <button
            type="button"
            className="btn-primary projects-new-btn"
            onClick={() => setShowCreate((v) => !v)}
          >
            {showCreate ? 'Close' : '+ New project'}
          </button>
        )}
      </div>

      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert success" role="status">{notice}</div>}

      {isProjectAdmin && showCreate && (
        <form className="content-panel projects-create" onSubmit={handleCreate} aria-label="Create project">
          <h2>New project</h2>
          <div className="form-grid">
            <div className="field-group">
              <label htmlFor="np-name">Name</label>
              <input
                id="np-name"
                className="field-input"
                value={createForm.name}
                maxLength={150}
                required
                onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="field-group">
              <label htmlFor="np-status">Initial status</label>
              <select
                id="np-status"
                className="field-select"
                value={createForm.status}
                onChange={(e) => setCreateForm((f) => ({ ...f, status: e.target.value }))}
              >
                <option value="planning">Planning</option>
                <option value="active">Active</option>
              </select>
            </div>
            <div className="field-group">
              <label htmlFor="np-start">Start date</label>
              <input
                id="np-start"
                type="date"
                className="field-input"
                value={createForm.startDate}
                onChange={(e) => setCreateForm((f) => ({ ...f, startDate: e.target.value }))}
              />
            </div>
            <div className="field-group">
              <label htmlFor="np-deadline">Deadline</label>
              <input
                id="np-deadline"
                type="date"
                className="field-input"
                value={createForm.deadline}
                onChange={(e) => setCreateForm((f) => ({ ...f, deadline: e.target.value }))}
              />
            </div>
          </div>
          <div className="field-group">
            <label htmlFor="np-desc">Description</label>
            <textarea
              id="np-desc"
              className="field-input"
              rows={2}
              value={createForm.description}
              onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          {createForm.status === 'active' && createForm.deadline && (
            <p className="muted-note">Weekly sprints are generated automatically up to the deadline.</p>
          )}
          <div className="projects-form-actions">
            <button type="submit" className="btn-primary" disabled={busy}>Create project</button>
          </div>
        </form>
      )}

      <div className="stat-row projects-stats">
        <div className="stat-card"><span className="stat-label">Projects</span><span className="stat-value">{counts.all}</span></div>
        <div className="stat-card"><span className="stat-label">Active</span><span className="stat-value">{counts.active}</span></div>
        <div className="stat-card"><span className="stat-label">On hold</span><span className="stat-value">{counts.on_hold}</span></div>
        <div className="stat-card"><span className="stat-label">Completed</span><span className="stat-value">{counts.completed}</span></div>
      </div>

      <div className="projects-toolbar">
        <input
          className="field-input projects-search"
          type="search"
          placeholder="Search projects, managers or leads…"
          aria-label="Search projects"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="filter-chips" role="tablist" aria-label="Filter by status">
          {['all', ...PROJECT_STATUSES].map((s) => (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={statusFilter === s}
              className={`filter-chip${statusFilter === s ? ' active' : ''}`}
              onClick={() => setStatusFilter(s)}
            >
              {s === 'all' ? 'All' : projectStatusLabel(s)} ({counts[s] || 0})
            </button>
          ))}
        </div>
      </div>

      {loading && <LoadingSpinner label="Loading projects…" />}

      {!loading && projects.length === 0 && (
        <div className="content-panel projects-empty">
          <p>{isProjectAdmin
            ? 'No projects yet — create the first one with “+ New project”.'
            : 'You are not assigned to any project yet.'}</p>
        </div>
      )}

      {!loading && projects.length > 0 && (
        <div className={`projects-layout${selected ? ' has-detail' : ''}`}>
          <div className="projects-grid">
            {visible.length === 0 && <p className="muted-note">No projects match this filter.</p>}
            {visible.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`project-card${p.id === selectedId ? ' is-selected' : ''}`}
                onClick={() => setSelectedId(p.id === selectedId ? null : p.id)}
                aria-pressed={p.id === selectedId}
              >
                <div className="project-card-top">
                  <strong className="project-card-name">{p.name}</strong>
                  <span className={`badge ${PROJECT_STATUS_BADGE[p.status] || 'blue'}`}>{projectStatusLabel(p.status)}</span>
                </div>
                {p.description && <p className="project-card-desc">{p.description}</p>}
                <div className="project-card-meta">
                  <span>👤 {p.manager ? p.manager.full_name : 'No manager'}</span>
                  <span>⭐ {p.team_lead ? p.team_lead.user.full_name : 'No team lead'}</span>
                  <span>👥 {p.member_count} member{p.member_count === 1 ? '' : 's'}</span>
                  {p.deadline && <span>📅 Due {formatDate(p.deadline)}</span>}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <aside className="content-panel project-detail" aria-label={`${selected.name} details`}>
              <div className="project-detail-head">
                <div>
                  <h2>{selected.name}</h2>
                  <span className={`badge ${PROJECT_STATUS_BADGE[selected.status] || 'blue'}`}>
                    {projectStatusLabel(selected.status)}
                  </span>
                </div>
                <button type="button" className="btn-link" onClick={() => setSelectedId(null)} aria-label="Close details">✕</button>
              </div>

              {!editing && (
                <>
                  <p className="detail-text">{selected.description || <span className="muted-note">No description.</span>}</p>
                  <div className="detail-meta-grid project-detail-dates">
                    <div><span className="dmeta-label">Start</span>{formatDate(selected.start_date)}</div>
                    <div><span className="dmeta-label">Deadline</span>{formatDate(selected.deadline)}</div>
                    <div><span className="dmeta-label">Created</span>{formatDate(selected.created_at)}</div>
                    {selected.completed_at && <div><span className="dmeta-label">Completed</span>{formatDate(selected.completed_at)}</div>}
                    {selected.cancelled_at && <div><span className="dmeta-label">Cancelled</span>{formatDate(selected.cancelled_at)}</div>}
                    {selected.archived_at && <div><span className="dmeta-label">Archived</span>{formatDate(selected.archived_at)}</div>}
                  </div>
                  {canEditProjectMetadata(role, userId, selected) && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => { setEditForm(editFormFrom(selected)); setEditing(true); }}
                    >
                      Edit details
                    </button>
                  )}
                </>
              )}

              {editing && editForm && (
                <form onSubmit={handleSaveEdit} className="project-edit-form" aria-label="Edit project">
                  <div className="field-group">
                    <label htmlFor="ep-name">Name</label>
                    <input
                      id="ep-name"
                      className="field-input"
                      value={editForm.name}
                      maxLength={150}
                      required
                      onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                    />
                  </div>
                  <div className="field-group">
                    <label htmlFor="ep-desc">Description</label>
                    <textarea
                      id="ep-desc"
                      className="field-input"
                      rows={3}
                      value={editForm.description}
                      onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
                    />
                  </div>
                  <div className="form-grid">
                    <div className="field-group">
                      <label htmlFor="ep-start">Start date</label>
                      <input
                        id="ep-start"
                        type="date"
                        className="field-input"
                        value={editForm.startDate}
                        onChange={(e) => setEditForm((f) => ({ ...f, startDate: e.target.value }))}
                      />
                    </div>
                    <div className="field-group">
                      <label htmlFor="ep-deadline">Deadline</label>
                      <input
                        id="ep-deadline"
                        type="date"
                        className="field-input"
                        value={editForm.deadline}
                        onChange={(e) => setEditForm((f) => ({ ...f, deadline: e.target.value }))}
                      />
                    </div>
                  </div>
                  <div className="projects-form-actions">
                    <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>Cancel</button>
                    <button type="submit" className="btn-primary" disabled={busy}>Save</button>
                  </div>
                </form>
              )}

              {canManageProject(role, userId, selected) && allowedNextStatuses(selected.status).length > 0 && (
                <div className="project-detail-section">
                  <h3 className="section-subheading">Lifecycle</h3>
                  <div className="project-transitions">
                    {allowedNextStatuses(selected.status).map((target) => (
                      <button
                        key={target}
                        type="button"
                        className={`btn-secondary transition-${target}`}
                        disabled={busy}
                        onClick={() => handleTransition(target)}
                      >
                        Move to {projectStatusLabel(target)}
                      </button>
                    ))}
                  </div>
                  {allowedNextStatuses(selected.status).includes('completed') && (
                    <p className="muted-note">Completion requires every sprint to be completed and every task done.</p>
                  )}
                </div>
              )}

              <div className="project-detail-section">
                <h3 className="section-subheading">People</h3>
                <div className="project-people">
                  <div><span className="dmeta-label">Manager</span>{selected.manager ? selected.manager.full_name : 'Not assigned'}</div>
                  <div><span className="dmeta-label">Team lead</span>{selected.team_lead ? selected.team_lead.user.full_name : 'Not assigned'}</div>
                </div>

                {isProjectAdmin && (
                  <div className="project-assign">
                    <div className="field-row">
                      <select
                        className="field-select"
                        aria-label="Choose project manager"
                        value={managerPick}
                        onChange={(e) => setManagerPick(e.target.value)}
                      >
                        <option value="">{activeManagers.length ? 'Set manager…' : 'No active Manager accounts'}</option>
                        {activeManagers.map((u) => (
                          <option key={u.id} value={u.id}>{u.full_name}</option>
                        ))}
                      </select>
                      <button type="button" className="btn-secondary" disabled={!managerPick || busy} onClick={handleAssignManager}>
                        Assign manager
                      </button>
                    </div>
                    <div className="field-row">
                      <select
                        className="field-select"
                        aria-label="Choose team lead"
                        value={leadPick}
                        onChange={(e) => setLeadPick(e.target.value)}
                      >
                        <option value="">{members.length ? 'Set team lead…' : 'No members on this project'}</option>
                        {members.map((emp) => (
                          <option key={emp.id} value={emp.id}>{emp.user.full_name}</option>
                        ))}
                      </select>
                      <button type="button" className="btn-secondary" disabled={!leadPick || busy} onClick={handleAssignLead}>
                        Assign lead
                      </button>
                    </div>
                  </div>
                )}

                {canSeeDirectory ? (
                  <ul className="project-members" aria-label="Project members">
                    {members.length === 0 && <li className="muted-note">No members assigned yet.</li>}
                    {members.map((emp) => (
                      <li key={emp.id}>
                        <Avatar name={emp.user.full_name} email={emp.user.email} size={30} />
                        <div className="project-member-text">
                          <strong>{emp.user.full_name}</strong>
                          <span className="muted-note">{emp.job_title}</span>
                        </div>
                        {selected.team_lead?.id === emp.id && <span className="badge green">Lead</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted-note">{selected.member_count} member{selected.member_count === 1 ? '' : 's'} on this project.</p>
                )}
              </div>

              {isProjectAdmin && (
                <div className="project-detail-section project-danger">
                  <button type="button" className="btn-link danger" disabled={busy} onClick={handleDelete}>
                    Delete project
                  </button>
                  <span className="muted-note">Only empty projects can be deleted — archive anything with history.</span>
                </div>
              )}
            </aside>
          )}
        </div>
      )}
    </div>
  );
}
