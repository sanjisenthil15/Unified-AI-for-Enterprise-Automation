/**
 * pages/EmployeeManagement/EmployeeManagement.js
 *
 * Admin / HR Manager only (enforced both by the backend and by App.js's
 * route-level ProtectedRoute). Onboards new hires (creates their login +
 * employee record together), manages the department list, and lets HR
 * update job title/department/status or terminate an employee.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  assignTeamLead, createDepartment, createEmployee, createProject,
  listDepartments, listEmployees, listProjects, terminateEmployee, updateEmployee,
} from '../../api/employeeApi';
import { listRoles } from '../../api/authApi';
import Avatar from '../../components/common/Avatar';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';

const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'intern'];
const STATUS_BADGE = { active: 'green', on_leave: 'amber', inactive: 'purple', terminated: 'red' };

const EMPTY_FORM = {
  fullName: '', email: '', roleId: '', jobTitle: '', departmentId: '', projectId: '',
  phone: '', hireDate: '', employmentType: 'full_time',
};

export default function EmployeeManagement() {
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [projects, setProjects] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [newDeptName, setNewDeptName] = useState('');
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDeadline, setNewProjectDeadline] = useState('');
  const [leadPicks, setLeadPicks] = useState({}); // { [projectId]: employeeId }
  const [justOnboarded, setJustOnboarded] = useState(null); // { employee, temporary_password }

  const load = useCallback(async () => {
    try {
      const [emps, depts, projs, rls] = await Promise.all([
        listEmployees(), listDepartments(), listProjects(), listRoles(),
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

  useEffect(() => { load(); }, [load]);

  function field(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleAddDepartment(e) {
    e.preventDefault();
    if (!newDeptName.trim()) return;
    try {
      await createDepartment({ name: newDeptName.trim() });
      setNewDeptName('');
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create department.');
    }
  }

  async function handleAddProject(e) {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    try {
      await createProject({ name: newProjectName.trim(), deadline: newProjectDeadline || null });
      setNewProjectName('');
      setNewProjectDeadline('');
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create project.');
    }
  }

  async function handleAssignLead(projectId) {
    const employeeId = leadPicks[projectId];
    if (!employeeId) return;
    try {
      await assignTeamLead(projectId, Number(employeeId));
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not assign team lead — they must already be a member of this project.');
    }
  }

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
      setJustOnboarded(result);
      setForm(EMPTY_FORM);
      setShowForm(false);
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not onboard this employee.');
    } finally {
      setSaving(false);
    }
  }

  async function handleStatusChange(id, status) {
    try {
      if (status === 'terminated') await terminateEmployee(id);
      else await updateEmployee(id, { status });
      load();
    } catch {
      setError('Could not update employee status.');
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
            Share this one-time temporary password with them — it won't be shown again:
          </p>
          <p className="temp-password-box">
            {justOnboarded.temporary_password}
          </p>
          <div style={{ marginTop: '0.75rem' }}>
            <button className="btn-secondary" onClick={() => setJustOnboarded(null)}>Dismiss</button>
          </div>
        </div>
      )}

      <div className="content-panel">
        <h2>Departments</h2>
        <div className="badge-row">
          {departments.map((d) => (
            <span key={d.id} className="badge blue">{d.name}</span>
          ))}
          {!departments.length && <span className="muted-note">No departments yet.</span>}
        </div>
        <form onSubmit={handleAddDepartment} className="field-row">
          <input
            className="field-input"
            placeholder="New department name"
            value={newDeptName}
            onChange={(e) => setNewDeptName(e.target.value)}
          />
          <button type="submit" className="btn-secondary">+ Add department</button>
        </form>
      </div>

      <div className="content-panel">
        <h2>Projects</h2>
        {projects.length === 0 && <p className="muted-note">No projects yet.</p>}
        {projects.map((p) => (
          <div key={p.id} className="list-row">
            <div className="list-row-main">
              <strong>{p.name}</strong>
              <span className="muted-note" style={{ marginLeft: '0.5rem' }}>
                {p.member_count} member{p.member_count === 1 ? '' : 's'}
              </span>
              <div>
                {p.team_lead
                  ? <span className="badge green">Lead: {p.team_lead.user.full_name}</span>
                  : <span className="badge amber">No team lead assigned</span>}
                {p.deadline && <span className="badge blue" style={{ marginLeft: '0.4rem' }}>Deadline: {p.deadline}</span>}
              </div>
            </div>
            <select
              className="field-select"
              value={leadPicks[p.id] || ''}
              onChange={(e) => setLeadPicks((picks) => ({ ...picks, [p.id]: e.target.value }))}
            >
              <option value="">Set team lead…</option>
              {employees.filter((emp) => emp.project?.id === p.id).map((emp) => (
                <option key={emp.id} value={emp.id}>{emp.user.full_name}</option>
              ))}
            </select>
            <button className="btn-secondary" onClick={() => handleAssignLead(p.id)} disabled={!leadPicks[p.id]}>
              Assign
            </button>
          </div>
        ))}
        <form onSubmit={handleAddProject} className="field-row" style={{ marginTop: '0.75rem' }}>
          <input
            className="field-input"
            placeholder="New project name"
            value={newProjectName}
            onChange={(e) => setNewProjectName(e.target.value)}
          />
          <input
            className="field-input"
            type="date"
            title="Deadline (optional)"
            value={newProjectDeadline}
            onChange={(e) => setNewProjectDeadline(e.target.value)}
          />
          <button type="submit" className="btn-secondary">+ Add project</button>
        </form>
      </div>

      <div className="content-panel">
        <div className="panel-header-row">
          <h2>Employee directory</h2>
          <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Close' : '+ Onboard employee'}
          </button>
        </div>

        {showForm && (
          <div className="job-form-box">
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
                  <input className="field-input" name="jobTitle" value={form.jobTitle} onChange={field}
                    placeholder="e.g. Software Engineer" required />
                </div>
                <div className="field-group">
                  <label>Role (access level) *</label>
                  <select className="field-select" name="roleId" value={form.roleId} onChange={field} required>
                    <option value="" disabled>Select a role</option>
                    {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
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

        {loading ? (
          <LoadingSpinner label="Loading employees…" />
        ) : employees.length === 0 ? (
          <p className="muted-note">No employees yet. Click "+ Onboard employee" to add one.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Job title</th>
                <th>Department</th>
                <th>Project</th>
                <th>Hire date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((emp) => (
                <tr key={emp.id}>
                  <td>
                    <div className="employee-name-cell">
                      <Avatar name={emp.user.full_name} email={emp.user.email} size={34} />
                      <div>
                        {emp.user.full_name}<br /><small className="muted-note">{emp.user.email}</small>
                      </div>
                    </div>
                  </td>
                  <td>{emp.job_title}</td>
                  <td>{emp.department?.name || '—'}</td>
                  <td>{emp.project?.name || '—'}</td>
                  <td>{emp.hire_date}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[emp.status] || 'purple'}`}>{emp.status.replace('_', ' ')}</span>
                  </td>
                  <td>
                    <select
                      className="field-select"
                      value={emp.status}
                      onChange={(e) => handleStatusChange(emp.id, e.target.value)}
                      disabled={emp.status === 'terminated'}
                    >
                      <option value="active">active</option>
                      <option value="on_leave">on_leave</option>
                      <option value="inactive">inactive</option>
                      <option value="terminated">terminated</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
