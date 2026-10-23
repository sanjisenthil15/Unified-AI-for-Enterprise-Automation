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
  createDepartment, createEmployee, listDepartments, listEmployees,
  terminateEmployee, updateEmployee,
} from '../../api/employeeApi';
import { listRoles } from '../../api/authApi';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';

const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'intern'];
const STATUS_BADGE = { active: 'green', on_leave: 'amber', inactive: 'purple', terminated: 'red' };

const EMPTY_FORM = {
  fullName: '', email: '', roleId: '', jobTitle: '', departmentId: '',
  phone: '', hireDate: '', employmentType: 'full_time',
};

export default function EmployeeManagement() {
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [newDeptName, setNewDeptName] = useState('');
  const [justOnboarded, setJustOnboarded] = useState(null); // { employee, temporary_password }

  const load = useCallback(async () => {
    try {
      const [emps, depts, rls] = await Promise.all([listEmployees(), listDepartments(), listRoles()]);
      setEmployees(emps);
      setDepartments(depts);
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
        <div className="content-panel" style={{ borderColor: '#166534' }}>
          <h2>✅ {justOnboarded.employee.user.full_name} onboarded</h2>
          <p>
            Share this one-time temporary password with them — it won't be shown again:
          </p>
          <p style={{ fontFamily: 'monospace', fontSize: '1.1rem', background: '#f0fdf4', padding: '0.5rem 1rem', borderRadius: 6, display: 'inline-block' }}>
            {justOnboarded.temporary_password}
          </p>
          <div style={{ marginTop: '0.75rem' }}>
            <button className="btn-secondary" onClick={() => setJustOnboarded(null)}>Dismiss</button>
          </div>
        </div>
      )}

      <div className="content-panel">
        <h2>Departments</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
          {departments.map((d) => (
            <span key={d.id} className="badge blue">{d.name}</span>
          ))}
          {!departments.length && <span style={{ color: 'var(--text-muted)' }}>No departments yet.</span>}
        </div>
        <form onSubmit={handleAddDepartment} style={{ display: 'flex', gap: '0.5rem' }}>
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h2 style={{ margin: 0 }}>Employee directory</h2>
          <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Close' : '+ Onboard employee'}
          </button>
        </div>

        {showForm && (
          <div className="job-form-box">
            <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '1rem' }}>Onboard a new employee</h3>
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
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving ? 'Onboarding…' : '+ Onboard employee'}
                </button>
                <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
              </div>
            </form>
          </div>
        )}

        {loading ? (
          <p>Loading…</p>
        ) : employees.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No employees yet. Click "+ Onboard employee" to add one.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                <th style={{ padding: '0.5rem' }}>Name</th>
                <th style={{ padding: '0.5rem' }}>Job title</th>
                <th style={{ padding: '0.5rem' }}>Department</th>
                <th style={{ padding: '0.5rem' }}>Hire date</th>
                <th style={{ padding: '0.5rem' }}>Status</th>
                <th style={{ padding: '0.5rem' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((emp) => (
                <tr key={emp.id} style={{ borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                  <td style={{ padding: '0.5rem' }}>{emp.user.full_name}<br /><small style={{ color: 'var(--text-muted)' }}>{emp.user.email}</small></td>
                  <td style={{ padding: '0.5rem' }}>{emp.job_title}</td>
                  <td style={{ padding: '0.5rem' }}>{emp.department?.name || '—'}</td>
                  <td style={{ padding: '0.5rem' }}>{emp.hire_date}</td>
                  <td style={{ padding: '0.5rem' }}>
                    <span className={`badge ${STATUS_BADGE[emp.status] || 'purple'}`}>{emp.status.replace('_', ' ')}</span>
                  </td>
                  <td style={{ padding: '0.5rem' }}>
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
