/**
 * pages/CustomerSupport/CustomerSupport.js
 *
 * Static presentation page for the Customer Support AI module.
 * No API calls — all data is hard-coded for demo purposes.
 */

import React from 'react';
import '../Recruitment/Recruitment.css';   // reuse shared module-page styles

const STATS = [
  { label: 'Open Tickets',    value: '43',  note: '8 critical' },
  { label: 'Resolved Today',  value: '27',  note: 'Avg 18 min' },
  { label: 'AI Auto-Replied', value: '19',  note: '70% of volume' },
  { label: 'Escalated',       value: '4',   note: 'Needs attention' },
];

const TICKETS = [
  { id: '#1042', subject: 'Cannot access my account',          priority: 'Critical', status: 'Open',        badge: 'red',    agent: 'AI Bot'       },
  { id: '#1041', subject: 'Invoice shows wrong amount',        priority: 'High',     status: 'In Progress', badge: 'amber',  agent: 'Sarah K.'     },
  { id: '#1040', subject: 'How do I reset my password?',       priority: 'Low',      status: 'Resolved',    badge: 'green',  agent: 'AI Bot'       },
  { id: '#1039', subject: 'Feature request — dark mode',       priority: 'Low',      status: 'Closed',      badge: 'green',  agent: 'Carlos R.'    },
  { id: '#1038', subject: 'App crashes on iOS 17',             priority: 'High',     status: 'Open',        badge: 'red',    agent: 'Unassigned'   },
  { id: '#1037', subject: 'Payment gateway timeout error',     priority: 'Critical', status: 'Escalated',   badge: 'red',    agent: 'Michael T.'   },
];

const PRIORITY_BADGE = {
  Critical: 'red',
  High:     'amber',
  Low:      'green',
};

export default function CustomerSupport() {
  return (
    <div className="module-page">

      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon purple" aria-hidden="true">🎧</div>
        <div>
          <h1>Customer Support</h1>
          <p>
            AI-powered ticket management with automatic replies, smart
            priority triage, and real-time escalation detection.
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

      {/* Ticket table */}
      <div className="content-panel">
        <h2>Active Support Tickets</h2>
        <table className="data-table" aria-label="Support ticket list">
          <thead>
            <tr>
              <th>Ticket ID</th>
              <th>Subject</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Assigned To</th>
            </tr>
          </thead>
          <tbody>
            {TICKETS.map((t) => (
              <tr key={t.id}>
                <td><strong>{t.id}</strong></td>
                <td>{t.subject}</td>
                <td>
                  <span className={`badge ${PRIORITY_BADGE[t.priority]}`}>
                    {t.priority}
                  </span>
                </td>
                <td>
                  <span className={`badge ${t.badge}`}>{t.status}</span>
                </td>
                <td>{t.agent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
