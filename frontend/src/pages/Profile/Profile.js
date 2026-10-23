/**
 * pages/Profile/Profile.js
 *
 * Any logged-in user's own read-only employee record. Open to everyone —
 * HR/admin manage the full directory at /employees; this is the
 * "helpful for every employee, not just HR" counterpart.
 */

import React, { useEffect, useState } from 'react';
import { getMyEmployeeRecord } from '../../api/employeeApi';
import '../Recruitment/Recruitment.css';

export default function Profile() {
  const [employee, setEmployee] = useState(null);
  const [notOnboarded, setNotOnboarded] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMyEmployeeRecord()
      .then(setEmployee)
      .catch((err) => {
        if (err.response?.status === 404) setNotOnboarded(true);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="module-page">
      <div className="module-page-header">
        <div className="module-page-icon green" aria-hidden="true">👤</div>
        <div><h1>My Profile</h1><p>Your employment record on file.</p></div>
      </div>

      <div className="content-panel">
        {loading ? (
          <p>Loading…</p>
        ) : notOnboarded ? (
          <p style={{ color: 'var(--text-muted)' }}>
            No employee record yet — contact HR to be onboarded.
          </p>
        ) : employee ? (
          <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: '0.75rem' }}>
            <dt style={{ fontWeight: 600 }}>Name</dt><dd>{employee.user.full_name}</dd>
            <dt style={{ fontWeight: 600 }}>Email</dt><dd>{employee.user.email}</dd>
            <dt style={{ fontWeight: 600 }}>Job title</dt><dd>{employee.job_title}</dd>
            <dt style={{ fontWeight: 600 }}>Department</dt><dd>{employee.department?.name || '—'}</dd>
            <dt style={{ fontWeight: 600 }}>Employment type</dt><dd>{employee.employment_type.replace('_', ' ')}</dd>
            <dt style={{ fontWeight: 600 }}>Hire date</dt><dd>{employee.hire_date}</dd>
            <dt style={{ fontWeight: 600 }}>Status</dt><dd><span className="badge green">{employee.status}</span></dd>
          </dl>
        ) : null}
      </div>
    </div>
  );
}
