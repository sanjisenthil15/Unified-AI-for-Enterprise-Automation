/**
 * pages/IncidentManagement/IncidentManagement.js
 *
 * Static presentation page for the Incident Management module.
 * No API calls — all data is hard-coded for demo purposes.
 */

import React from 'react';
import '../Recruitment/Recruitment.css';   // reuse shared module-page styles

const STATS = [
  { label: 'Open Incidents',  value: '9',   note: '2 critical' },
  { label: 'Resolved Today',  value: '14',  note: 'Avg 42 min' },
  { label: 'MTTR',            value: '38m', note: '↓ 12% vs last week' },
  { label: 'AI Triaged',      value: '21',  note: 'This week' },
];

const INCIDENTS = [
  { id: 'INC-0091', title: 'Production DB connection pool exhausted',  severity: 'Critical', status: 'Investigating', badge: 'red',    assignee: 'DevOps Team'   },
  { id: 'INC-0090', title: 'API gateway returning 502 for /payments',  severity: 'High',     status: 'Open',          badge: 'amber',  assignee: 'Platform Team' },
  { id: 'INC-0089', title: 'Auth service latency spike > 3 s',         severity: 'High',     status: 'Resolved',      badge: 'green',  assignee: 'James O.'      },
  { id: 'INC-0088', title: 'Email notifications delayed by 30 min',    severity: 'Medium',   status: 'Open',          badge: 'amber',  assignee: 'Unassigned'    },
  { id: 'INC-0087', title: 'iOS app crash on startup (v4.1.2)',         severity: 'High',     status: 'Resolved',      badge: 'green',  assignee: 'Mobile Team'   },
  { id: 'INC-0086', title: 'Scheduled reports not sending overnight',  severity: 'Medium',   status: 'Closed',        badge: 'green',  assignee: 'Aisha P.'      },
];

const SEV_BADGE = { Critical: 'red', High: 'amber', Medium: 'blue', Low: 'green' };

export default function IncidentManagement() {
  return (
    <div className="module-page">

      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon red" aria-hidden="true">🚨</div>
        <div>
          <h1>Incident Management</h1>
          <p>
            Log, triage, and resolve incidents faster. AI suggests severity
            and routes each incident to the right team automatically.
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="stat-row">
        {STATS.map((s) => (
          <div key={s.label} className="stat-card">
            <div className="stat-label">{s.label}</div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-note">{s.note}</div>
          </div>
        ))}
      </div>

      {/* Incident table */}
      <div className="content-panel">
        <h2>Recent Incidents</h2>
        <table className="data-table" aria-label="Incident list">
          <thead>
            <tr>
              <th>Incident ID</th>
              <th>Title</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Assigned To</th>
            </tr>
          </thead>
          <tbody>
            {INCIDENTS.map((inc) => (
              <tr key={inc.id}>
                <td><strong>{inc.id}</strong></td>
                <td>{inc.title}</td>
                <td>
                  <span className={`badge ${SEV_BADGE[inc.severity]}`}>
                    {inc.severity}
                  </span>
                </td>
                <td>
                  <span className={`badge ${inc.badge}`}>{inc.status}</span>
                </td>
                <td>{inc.assignee}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
