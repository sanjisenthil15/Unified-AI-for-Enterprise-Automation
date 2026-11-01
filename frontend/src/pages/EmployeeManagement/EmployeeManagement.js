/**
 * pages/EmployeeManagement/EmployeeManagement.js
 *
 * Admin / HR Manager directory & workforce administration.
 * Features:
 *  - Employee Directory with live search, department/project/role filters
 *  - Circular avatar photos with initials fallback
 *  - Role badges and employment details
 *  - Onboard new employee workflow with temporary password generation
 *  - Edit employee modal (job title, department, project assignment, role)
 *  - Interactive password reset for employees
 *  - Project management (Manager & Team Lead assignment, lifecycle status updates)
 *  - Toast feedback and subtle row/card highlight animations
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  assignProjectManager,
  assignTeamLead,
  createDepartment,
  createEmployee,
  createProject,
  deleteProject,
  listDepartments,
  listEmployees,
  listProjects,
  terminateEmployee,
  updateEmployee,
  updateProjectStatus,
} from '../../api/employeeApi';
import { listRoles, resetUserPassword } from '../../api/authApi';
import Avatar from '../../components/common/Avatar';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import Toast from '../../components/common/Toast';
import { useToast } from '../../hooks/useToast';
import { apiErrorText } from '../../utils/passwordPolicy';
import {
  PROJECT_STATUS_BADGE,
  allowedNextStatuses,
  projectStatusLabel,
} from '../../utils/projectLifecycle';
import './EmployeeManagement.css';

const PASSWORD_RESET_ROLES = ['admin', 'hr_manager'];
const PEOPLE_ADMIN_ROLES = ['admin', 'hr_manager'];

function currentRole() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.role?.name?.toLowerCase() ?? '';
  } catch {
    return '';
  }
}

const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'intern'];
const STATUS_BADGE = {
  active: 'green',
  on_leave: 'amber',
  inactive: 'purple',
  terminated: 'red',
};

const EMPTY_FORM = {
  fullName: '',
  email: '',
  roleId: '',
  jobTitle: '',
  departmentId: '',
  projectId: '',
  phone: '',
  hireDate: '',
  employmentType: 'full_time',
};

function formatRoleLabel(roleName) {
  if (!roleName) return 'Employee';
  if (roleName === 'hr_manager') return 'HR Manager';
  if (roleName === 'support_agent') return 'Support Agent';
  if (roleName === 'team_lead') return 'Team Lead';
  return roleName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function EmployeeManagement() {
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [projects, setProjects] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Toast system
  const { toast, showToast, dismissToast } = useToast();

  // Highlighted row/card IDs for brief animation feedback
  const [highlightedRowId, setHighlightedRowId] = useState(null);
  const [highlightedCardId, setHighlightedCardId] = useState(null);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [filterRole, setFilterRole] = useState('');
  const [filterDept, setFilterDept] = useState('');
  const [filterProj, setFilterProj] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  // Onboard Form state
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // Edit Employee Modal state
  const [editingEmp, setEditingEmp] = useState(null);
  const [editForm, setEditForm] = useState({
    jobTitle: '',
    departmentId: '',
    projectId: '',
    roleId: '',
    employmentType: 'full_time',
  });
  const [savingEdit, setSavingEdit] = useState(false);

  // Departments & Projects inputs
  const [newDeptName, setNewDeptName] = useState('');
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectStartDate, setNewProjectStartDate] = useState('');
  const [newProjectDeadline, setNewProjectDeadline] = useState('');
  const [addingDept, setAddingDept] = useState(false);
  const [addingProject, setAddingProject] = useState(false);

  // Project assignments state
  const [leadPicks, setLeadPicks] = useState({});
  const [managerPicks, setManagerPicks] = useState({});
  const [statusPicks, setStatusPicks] = useState({});
  const [busyProjectId, setBusyProjectId] = useState(null);

  // Temporary password display
  const [justOnboarded, setJustOnboarded] = useState(null);
  const [justReset, setJustReset] = useState(null);
  const [resettingId, setResettingId] = useState(null);

  const canResetPasswords = PASSWORD_RESET_ROLES.includes(currentRole());
  const canManagePeople = PEOPLE_ADMIN_ROLES.includes(currentRole());

  const triggerRowHighlight = (id) => {
    setHighlightedRowId(id);
    setTimeout(() => setHighlightedRowId(null), 2200);
  };

  const triggerCardHighlight = (id) => {
    setHighlightedCardId(id);
    setTimeout(() => setHighlightedCardId(null), 2200);
  };

  const load = useCallback(async () => {
    try {
      const [emps, depts, projs, rls] = await Promise.all([
        listEmployees(),
        listDepartments(),
        listProjects(),
        listRoles(),
      ]);
      setEmployees(emps);
      setDepartments(depts);
      setProjects(projs);
      setRoles(rls);
      setError('');
    } catch {
      setError('Could not load employee data. Check backend availability.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Filtered employees memo
  const filteredEmployees = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return employees.filter((emp) => {
      const name = emp.user?.full_name?.toLowerCase() || '';
      const email = emp.user?.email?.toLowerCase() || '';
      const job = emp.job_title?.toLowerCase() || '';
      const matchesSearch = !q || name.includes(q) || email.includes(q) || job.includes(q);

      const matchesRole = !filterRole || emp.user?.role?.name === filterRole;
      const matchesDept = !filterDept || String(emp.department_id) === String(filterDept);
      const matchesProj = !filterProj || String(emp.project_id) === String(filterProj);
      const matchesStatus = !filterStatus || emp.status === filterStatus;

      return matchesSearch && matchesRole && matchesDept && matchesProj && matchesStatus;
    });
  }, [employees, searchQuery, filterRole, filterDept, filterProj, filterStatus]);

  function field(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  }

  // ── 1. Department Creation ──────────────────────────────────────────
  async function handleAddDepartment(e) {
    e.preventDefault();
    if (!newDeptName.trim() || addingDept) return;
    setAddingDept(true);
    try {
      await createDepartment({ name: newDeptName.trim() });
      setNewDeptName('');
      await load();
      showToast(`Department "${newDeptName.trim()}" created successfully.`, 'success');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Could not create department.';
      showToast(msg, 'error');
    } finally {
      setAddingDept(false);
    }
  }

  // ── 2. Project Creation ─────────────────────────────────────────────
  async function handleAddProject(e) {
    e.preventDefault();
    if (!newProjectName.trim() || addingProject) return;
    setAddingProject(true);
    try {
      const p = await createProject({
        name: newProjectName.trim(),
        startDate: newProjectStartDate || null,
        deadline: newProjectDeadline || null,
      });
      setNewProjectName('');
      setNewProjectStartDate('');
      setNewProjectDeadline('');
      await load();
      showToast(`Project "${p.name}" created successfully.`, 'success');
      if (p.id) triggerCardHighlight(p.id);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Could not create project.';
      showToast(msg, 'error');
    } finally {
      setAddingProject(false);
    }
  }

  // ── 3. Project Status Update ────────────────────────────────────────
  async function handleProjectStatusChange(projectId) {
    const nextStatus = statusPicks[projectId];
    if (!nextStatus || busyProjectId === projectId) return;
    setBusyProjectId(projectId);
    try {
      await updateProjectStatus(projectId, nextStatus);
      setStatusPicks((picks) => ({ ...picks, [projectId]: '' }));
      await load();
      showToast(`Project status updated to ${projectStatusLabel(nextStatus)}.`, 'success');
      triggerCardHighlight(projectId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not update project status.', 'error');
    } finally {
      setBusyProjectId(null);
    }
  }

  // ── 4. Project Deletion ─────────────────────────────────────────────
  async function handleDeleteProject(projectId) {
    // eslint-disable-next-line no-alert
    if (!window.confirm('Are you sure you want to delete this project? Only empty projects without sprints or members can be deleted.')) {
      return;
    }
    setBusyProjectId(projectId);
    try {
      await deleteProject(projectId);
      await load();
      showToast('Project deleted successfully.', 'success');
    } catch (err) {
      const detail = err.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not delete project. You may need to archive it instead.', 'error');
    } finally {
      setBusyProjectId(null);
    }
  }

  // ── 5. Assign Team Lead ─────────────────────────────────────────────
  async function handleAssignLead(projectId) {
    const employeeId = leadPicks[projectId];
    if (!employeeId || busyProjectId === projectId) return;
    setBusyProjectId(projectId);
    try {
      await assignTeamLead(projectId, Number(employeeId));
      await load();
      showToast('Team Lead assigned successfully.', 'success');
      triggerCardHighlight(projectId);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Could not assign team lead — they must already be a member of this project.';
      showToast(msg, 'error');
    } finally {
      setBusyProjectId(null);
    }
  }

  // ── 6. Assign Manager ───────────────────────────────────────────────
  async function handleAssignManager(projectId) {
    const managerUserId = managerPicks[projectId];
    if (!managerUserId || busyProjectId === projectId) return;
    setBusyProjectId(projectId);
    try {
      await assignProjectManager(projectId, Number(managerUserId));
      setManagerPicks((picks) => ({ ...picks, [projectId]: '' }));
      await load();
      showToast('Project Manager assigned successfully.', 'success');
      triggerCardHighlight(projectId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not assign project manager.', 'error');
    } finally {
      setBusyProjectId(null);
    }
  }

  // ── 7. Onboard Employee ─────────────────────────────────────────────
  async function handleOnboard(e) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const result = await createEmployee({
        fullName: form.fullName.trim(),
        email: form.email.trim(),
        roleId: Number(form.roleId),
        jobTitle: form.jobTitle.trim(),
        departmentId: form.departmentId ? Number(form.departmentId) : null,
        projectId: form.projectId ? Number(form.projectId) : null,
        phone: form.phone.trim() || null,
        hireDate: form.hireDate,
        employmentType: form.employmentType,
      });
      setJustReset(null);
      setJustOnboarded(result);
      setForm(EMPTY_FORM);
      setShowForm(false);
      await load();
      showToast(`Employee ${result.employee.user.full_name} onboarded successfully!`, 'success');
      triggerRowHighlight(result.employee.id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : 'Could not onboard this employee.';
      setError(msg);
      showToast(msg, 'error');
    } finally {
      setSaving(false);
    }
  }

  // ── 8. Status Change / Deactivate ───────────────────────────────────
  async function handleStatusChange(id, status) {
    try {
      if (status === 'terminated') {
        await terminateEmployee(id);
      } else {
        await updateEmployee(id, { status });
      }
      await load();
      showToast(`Employee status updated to ${status.replace('_', ' ')}.`, 'success');
      triggerRowHighlight(id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not update employee status.', 'error');
    }
  }

  // ── 9. Edit Employee Modal ──────────────────────────────────────────
  function openEditModal(emp) {
    setEditingEmp(emp);
    setEditForm({
      jobTitle: emp.job_title || '',
      departmentId: emp.department_id ? String(emp.department_id) : '',
      projectId: emp.project_id ? String(emp.project_id) : '',
      roleId: emp.user?.role_id ? String(emp.user.role_id) : '',
      employmentType: emp.employment_type || 'full_time',
    });
  }

  async function handleSaveEdit(e) {
    e.preventDefault();
    if (!editingEmp || savingEdit) return;
    setSavingEdit(true);
    try {
      const payload = {
        job_title: editForm.jobTitle.trim(),
        department_id: editForm.departmentId ? Number(editForm.departmentId) : null,
        project_id: editForm.projectId ? Number(editForm.projectId) : null,
        role_id: editForm.roleId ? Number(editForm.roleId) : null,
        employment_type: editForm.employmentType,
      };
      await updateEmployee(editingEmp.id, payload);
      const empName = editingEmp.user?.full_name;
      const targetId = editingEmp.id;
      setEditingEmp(null);
      await load();
      showToast(`Employee ${empName} updated successfully.`, 'success');
      triggerRowHighlight(targetId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      showToast(typeof detail === 'string' ? detail : 'Could not update employee details.', 'error');
    } finally {
      setSavingEdit(false);
    }
  }

  // ── 10. Reset Password ──────────────────────────────────────────────
  async function handleResetPassword(emp) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(
      `Reset the password for ${emp.user.full_name}?\n\n`
      + 'They will be signed out everywhere and must set a new password the next time they sign in.',
    )) return;
    setResettingId(emp.id);
    setError('');
    try {
      const result = await resetUserPassword(emp.user.id);
      setJustOnboarded(null);
      setJustReset({ name: emp.user.full_name, temporary_password: result.temporary_password });
      showToast(`Temporary password issued for ${emp.user.full_name}.`, 'success');
    } catch (err) {
      const msg = apiErrorText(err, 'Could not reset this password.');
      setError(msg);
      showToast(msg, 'error');
    } finally {
      setResettingId(null);
    }
  }

  return (
    <div className="module-page">
      <div className="module-page-header">
        <div className="module-page-icon purple" aria-hidden="true">👥</div>
        <div>
          <h1>Employee Management</h1>
          <p>Onboard new hires, manage departments, and keep the employee directory up to date.</p>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      {justOnboarded && (
        <div className="content-panel success-panel">
          <h2>✅ {justOnboarded.employee.user.full_name} onboarded</h2>
          <p>
            Share this one-time temporary password with them privately — it won't be shown again:
          </p>
          <p className="temp-password-box">
            {justOnboarded.temporary_password}
          </p>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            The first time they sign in they'll be asked to replace it with a password of their own,
            and they can't use the app until they do.
          </p>
          <div style={{ marginTop: '0.75rem' }}>
            <button className="btn-secondary" onClick={() => setJustOnboarded(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {justReset && (
        <div className="content-panel success-panel">
          <h2>🔑 Password reset for {justReset.name}</h2>
          <p>
            Share this one-time temporary password with them privately — it won't be shown again:
          </p>
          <p className="temp-password-box">
            {justReset.temporary_password}
          </p>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Their existing sessions have been signed out, and they must choose a new password at their next sign-in.
          </p>
          <div style={{ marginTop: '0.75rem' }}>
            <button className="btn-secondary" onClick={() => setJustReset(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {/* Departments Panel */}
      <div className="content-panel">
        <h2>Departments</h2>
        <div className="badge-row">
          {departments.map((d) => (
            <span key={d.id} className="badge blue">{d.name}</span>
          ))}
          {!departments.length && <span className="muted-note">No departments yet.</span>}
        </div>
        {canManagePeople && (
          <form onSubmit={handleAddDepartment} className="field-row">
            <input
              className="field-input"
              placeholder="New department name"
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              disabled={addingDept}
            />
            <button type="submit" className="btn-secondary" disabled={addingDept || !newDeptName.trim()}>
              {addingDept ? 'Adding…' : '+ Add department'}
            </button>
          </form>
        )}
      </div>

      {/* Projects Panel */}
      <div className="content-panel">
        <div className="panel-header-row">
          <h2>Projects</h2>
          <Link to="/projects" className="btn-link">Open the Projects page →</Link>
        </div>
        {projects.length === 0 && <p className="muted-note">No projects yet.</p>}
        {projects.map((p) => {
          const activeManagers = employees.filter(
            (emp) => emp.user?.role?.name === 'manager' && emp.user?.is_active && emp.status === 'active',
          ).map((emp) => emp.user);

          const allowedNext = allowedNextStatuses(p.status);
          const isBusy = busyProjectId === p.id;
          const isCardHighlighted = highlightedCardId === p.id;

          return (
            <div
              key={p.id}
              className={`list-row ${isCardHighlighted ? 'card-updated-highlight' : ''}`}
              style={{ flexWrap: 'wrap', gap: '0.5rem', transition: 'all 0.2s' }}
            >
              <div className="list-row-main" style={{ minWidth: '220px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <strong>{p.name}</strong>
                  <span className={`badge ${PROJECT_STATUS_BADGE[p.status] || 'blue'}`}>
                    {projectStatusLabel(p.status)}
                  </span>
                </div>
                <span className="muted-note" style={{ marginLeft: '0.5rem' }}>
                  {p.member_count} member{p.member_count === 1 ? '' : 's'}
                </span>
                <div style={{ marginTop: '0.3rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                  {p.manager
                    ? <span className="badge purple">Manager: {p.manager.full_name}</span>
                    : <span className="badge amber">No manager assigned</span>}
                  {p.team_lead
                    ? <span className="badge green">Lead: {p.team_lead.user.full_name}</span>
                    : <span className="badge amber">No team lead assigned</span>}
                  {p.start_date && <span className="badge blue">Start: {p.start_date}</span>}
                  {p.deadline && <span className="badge blue">Deadline: {p.deadline}</span>}
                  {p.completed_at && <span className="badge green">Completed: {new Date(p.completed_at).toLocaleDateString()}</span>}
                  {p.cancelled_at && <span className="badge red">Cancelled: {new Date(p.cancelled_at).toLocaleDateString()}</span>}
                  {p.archived_at && <span className="badge purple">Archived: {new Date(p.archived_at).toLocaleDateString()}</span>}
                </div>
              </div>

              {/* Status transition control */}
              {allowedNext.length > 0 && (
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <select
                    className="field-select"
                    value={statusPicks[p.id] || ''}
                    onChange={(e) => setStatusPicks((picks) => ({ ...picks, [p.id]: e.target.value }))}
                    disabled={isBusy}
                  >
                    <option value="">Change status…</option>
                    {allowedNext.map((st) => (
                      <option key={st} value={st}>{projectStatusLabel(st)}</option>
                    ))}
                  </select>
                  <button
                    className="btn-secondary"
                    onClick={() => handleProjectStatusChange(p.id)}
                    disabled={!statusPicks[p.id] || isBusy}
                  >
                    {isBusy ? 'Updating…' : 'Update'}
                  </button>
                </div>
              )}

              {/* Manager assignment (Admin / HR) */}
              {canManagePeople && (
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <select
                    className="field-select"
                    value={managerPicks[p.id] || ''}
                    onChange={(e) => setManagerPicks((picks) => ({ ...picks, [p.id]: e.target.value }))}
                    disabled={isBusy}
                  >
                    <option value="">Set manager…</option>
                    {activeManagers.map((mgr) => (
                      <option key={mgr.id} value={mgr.id}>{mgr.full_name} ({mgr.email})</option>
                    ))}
                  </select>
                  <button
                    className="btn-secondary"
                    onClick={() => handleAssignManager(p.id)}
                    disabled={!managerPicks[p.id] || isBusy}
                  >
                    {isBusy ? 'Assigning…' : 'Assign Manager'}
                  </button>
                </div>
              )}

              {/* Team Lead assignment (Admin / HR) */}
              {canManagePeople && (
                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <select
                    className="field-select"
                    value={leadPicks[p.id] || ''}
                    onChange={(e) => setLeadPicks((picks) => ({ ...picks, [p.id]: e.target.value }))}
                    disabled={isBusy}
                  >
                    <option value="">Set team lead…</option>
                    {employees.filter((emp) => emp.project?.id === p.id).map((emp) => (
                      <option key={emp.id} value={emp.id}>{emp.user.full_name}</option>
                    ))}
                  </select>
                  <button
                    className="btn-secondary"
                    onClick={() => handleAssignLead(p.id)}
                    disabled={!leadPicks[p.id] || isBusy}
                  >
                    {isBusy ? 'Assigning…' : 'Assign Lead'}
                  </button>
                </div>
              )}

              {/* Delete button (Admin / HR) */}
              {canManagePeople && (
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <button
                    className="btn-secondary"
                    style={{ color: '#ef4444', borderColor: '#ef4444' }}
                    onClick={() => handleDeleteProject(p.id)}
                    title="Delete unassociated project"
                    disabled={isBusy}
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>
          );
        })}

        {canManagePeople && (
          <form onSubmit={handleAddProject} className="field-row" style={{ marginTop: '0.75rem', flexWrap: 'wrap' }}>
            <input
              className="field-input"
              placeholder="New project name"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              disabled={addingProject}
            />
            <input
              className="field-input"
              type="date"
              title="Start date (optional)"
              value={newProjectStartDate}
              onChange={(e) => setNewProjectStartDate(e.target.value)}
              disabled={addingProject}
            />
            <input
              className="field-input"
              type="date"
              title="Deadline (optional)"
              value={newProjectDeadline}
              onChange={(e) => setNewProjectDeadline(e.target.value)}
              disabled={addingProject}
            />
            <button type="submit" className="btn-secondary" disabled={addingProject || !newProjectName.trim()}>
              {addingProject ? 'Adding…' : '+ Add project'}
            </button>
          </form>
        )}
      </div>

      {/* Employee Directory Panel */}
      <div className="content-panel">
        <div className="panel-header-row">
          <h2>Employee directory</h2>
          {canManagePeople && (
            <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
              {showForm ? 'Close' : '+ Onboard employee'}
            </button>
          )}
        </div>

        {/* Onboarding Form */}
        {canManagePeople && showForm && (
          <div className="job-form-box" style={{ animation: 'modalDialogSlideIn 0.25s ease-out' }}>
            <h3 className="section-subheading" style={{ marginTop: 0 }}>Onboard a new employee</h3>
            <form onSubmit={handleOnboard}>
              <div className="form-grid">
                <div className="field-group">
                  <label>Full name *</label>
                  <input className="field-input" name="fullName" value={form.fullName} onChange={field} required />
                </div>
                <div className="field-group">
                  <label>Email *</label>
                  <input className="field-input" type="email" name="email" value={form.email} onChange={field} required />
                </div>
                <div className="field-group">
                  <label>Job title *</label>
                  <input
                    className="field-input"
                    name="jobTitle"
                    value={form.jobTitle}
                    onChange={field}
                    placeholder="e.g. Software Engineer"
                    required
                  />
                </div>
                <div className="field-group">
                  <label>Role (access level) *</label>
                  <select className="field-select" name="roleId" value={form.roleId} onChange={field} required>
                    <option value="" disabled>Select a role</option>
                    {roles.map((r) => <option key={r.id} value={r.id}>{formatRoleLabel(r.name)}</option>)}
                  </select>
                </div>
                <div className="field-group">
                  <label>Department</label>
                  <select className="field-select" name="departmentId" value={form.departmentId} onChange={field}>
                    <option value="">None</option>
                    {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </div>
                <div className="field-group">
                  <label>Project</label>
                  <select className="field-select" name="projectId" value={form.projectId} onChange={field}>
                    <option value="">None</option>
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div className="field-group">
                  <label>Employment type</label>
                  <select className="field-select" name="employmentType" value={form.employmentType} onChange={field}>
                    {EMPLOYMENT_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                  </select>
                </div>
                <div className="field-group">
                  <label>Hire date *</label>
                  <input className="field-input" type="date" name="hireDate" value={form.hireDate} onChange={field} required />
                </div>
                <div className="field-group">
                  <label>Phone</label>
                  <input className="field-input" name="phone" value={form.phone} onChange={field} />
                </div>
              </div>
              <div className="field-row" style={{ marginTop: '1rem' }}>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Onboarding…' : '+ Onboard employee'}
                </button>
                <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
              </div>
            </form>
          </div>
        )}

        {/* Search & Filter Toolbar */}
        <div className="employee-controls-bar">
          <div className="employee-search-box">
            <span className="employee-search-icon" aria-hidden="true">🔍</span>
            <input
              type="text"
              placeholder="Search by name, email, or job title…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="employee-filters-group">
            <select value={filterRole} onChange={(e) => setFilterRole(e.target.value)}>
              <option value="">All Roles</option>
              {roles.map((r) => <option key={r.id} value={r.name}>{formatRoleLabel(r.name)}</option>)}
            </select>

            <select value={filterDept} onChange={(e) => setFilterDept(e.target.value)}>
              <option value="">All Departments</option>
              {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>

            <select value={filterProj} onChange={(e) => setFilterProj(e.target.value)}>
              <option value="">All Projects</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>

            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="on_leave">On Leave</option>
              <option value="inactive">Inactive</option>
              <option value="terminated">Terminated</option>
            </select>

            <span className="filter-count-badge">
              {filteredEmployees.length} of {employees.length}
            </span>
          </div>
        </div>

        {/* Employee Table */}
        {loading ? (
          <LoadingSpinner label="Loading employees…" />
        ) : filteredEmployees.length === 0 ? (
          <p className="muted-note">
            {employees.length === 0
              ? 'No employees yet. Click "+ Onboard employee" to add one.'
              : 'No employees match the selected search or filter criteria.'}
          </p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name & Role</th>
                <th>Job title</th>
                <th>Department</th>
                <th>Project</th>
                <th>Hire date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEmployees.map((emp) => {
                const isHighlighted = highlightedRowId === emp.id;
                const roleName = emp.user?.role?.name || 'employee';

                return (
                  <tr key={emp.id} className={isHighlighted ? 'row-updated-highlight' : ''}>
                    <td>
                      <div className="employee-name-cell">
                        <Avatar name={emp.user.full_name} email={emp.user.email} size={36} />
                        <div>
                          <strong>{emp.user.full_name}</strong>
                          <div>
                            <span className={`role-badge role-${roleName}`}>
                              {formatRoleLabel(roleName)}
                            </span>
                          </div>
                          <small className="muted-note">{emp.user.email}</small>
                        </div>
                      </div>
                    </td>
                    <td>{emp.job_title}</td>
                    <td>{emp.department?.name || '—'}</td>
                    <td>{emp.project?.name || '—'}</td>
                    <td>{emp.hire_date}</td>
                    <td>
                      <span className={`badge ${STATUS_BADGE[emp.status] || 'purple'}`}>
                        {emp.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      {!canManagePeople && <span className="muted-note">View only</span>}
                      {canManagePeople && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                          <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                            <select
                              className="field-select"
                              style={{ fontSize: '0.78rem', padding: '0.25rem 0.5rem' }}
                              value={emp.status}
                              onChange={(e) => handleStatusChange(emp.id, e.target.value)}
                              disabled={emp.status === 'terminated'}
                            >
                              <option value="active">active</option>
                              <option value="on_leave">on_leave</option>
                              <option value="inactive">inactive</option>
                              <option value="terminated">terminated</option>
                            </select>

                            <button
                              type="button"
                              className="btn-secondary"
                              style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
                              onClick={() => openEditModal(emp)}
                              disabled={emp.status === 'terminated'}
                              title="Edit job title, role, project, or department"
                            >
                              Edit
                            </button>
                          </div>

                          {canResetPasswords && emp.status !== 'terminated' && (
                            <button
                              type="button"
                              className="btn-secondary"
                              style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem', color: '#6366f1' }}
                              onClick={() => handleResetPassword(emp)}
                              disabled={resettingId === emp.id}
                            >
                              {resettingId === emp.id ? 'Resetting…' : 'Reset password'}
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Edit Employee Modal */}
      {editingEmp && (
        <div className="modal-overlay" onClick={() => !savingEdit && setEditingEmp(null)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Edit {editingEmp.user.full_name}</h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => !savingEdit && setEditingEmp(null)}
                disabled={savingEdit}
              >
                ×
              </button>
            </div>
            <form onSubmit={handleSaveEdit}>
              <div className="modal-body">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', marginBottom: '1.25rem' }}>
                  <Avatar name={editingEmp.user.full_name} email={editingEmp.user.email} size={48} />
                  <div>
                    <strong>{editingEmp.user.full_name}</strong>
                    <div className="muted-note" style={{ fontSize: '0.82rem' }}>{editingEmp.user.email}</div>
                  </div>
                </div>

                <div className="field-group" style={{ marginBottom: '0.85rem' }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                    Job Title *
                  </label>
                  <input
                    className="field-input"
                    value={editForm.jobTitle}
                    onChange={(e) => setEditForm((f) => ({ ...f, jobTitle: e.target.value }))}
                    required
                  />
                </div>

                <div className="field-group" style={{ marginBottom: '0.85rem' }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                    Role (Access Level) *
                  </label>
                  <select
                    className="field-select"
                    value={editForm.roleId}
                    onChange={(e) => setEditForm((f) => ({ ...f, roleId: e.target.value }))}
                    required
                  >
                    {roles.map((r) => (
                      <option key={r.id} value={r.id}>{formatRoleLabel(r.name)}</option>
                    ))}
                  </select>
                </div>

                <div className="field-group" style={{ marginBottom: '0.85rem' }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                    Project Assignment
                  </label>
                  <select
                    className="field-select"
                    value={editForm.projectId}
                    onChange={(e) => setEditForm((f) => ({ ...f, projectId: e.target.value }))}
                  >
                    <option value="">None (Unassigned)</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>

                <div className="field-group" style={{ marginBottom: '0.85rem' }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                    Department
                  </label>
                  <select
                    className="field-select"
                    value={editForm.departmentId}
                    onChange={(e) => setEditForm((f) => ({ ...f, departmentId: e.target.value }))}
                  >
                    <option value="">None</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </div>

                <div className="field-group">
                  <label style={{ fontSize: '0.82rem', fontWeight: 600, display: 'block', marginBottom: '0.3rem' }}>
                    Employment Type
                  </label>
                  <select
                    className="field-select"
                    value={editForm.employmentType}
                    onChange={(e) => setEditForm((f) => ({ ...f, employmentType: e.target.value }))}
                  >
                    {EMPLOYMENT_TYPES.map((t) => (
                      <option key={t} value={t}>{t.replace('_', ' ')}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setEditingEmp(null)}
                  disabled={savingEdit}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={savingEdit}>
                  {savingEdit ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Floating Toast notification container */}
      <div className="app-toast-container">
        {toast && (
          <Toast
            message={toast.message}
            type={toast.type}
            onClose={dismissToast}
          />
        )}
      </div>
    </div>
  );
}
