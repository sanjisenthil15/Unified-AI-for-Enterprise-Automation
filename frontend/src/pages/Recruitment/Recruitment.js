/**
 * pages/Recruitment/Recruitment.js
 *
 * Static presentation page for the AI Recruitment module.
 * No API calls — all data is hard-coded for demo purposes.
 */

import React from 'react';
import './Recruitment.css';

const STATS = [
  { label: 'Open Positions',  value: '12',  note: '+3 this week' },
  { label: 'Applications',    value: '148', note: '+24 today' },
  { label: 'Shortlisted',     value: '31',  note: 'AI screened' },
  { label: 'Interviews Today',value: '6',   note: 'Scheduled' },
];

const CANDIDATES = [
  { name: 'Sarah Johnson',  role: 'Senior Python Developer', score: '94%', status: 'Shortlisted',  badge: 'green'  },
  { name: 'Michael Chen',   role: 'DevOps Engineer',         score: '88%', status: 'Interview',    badge: 'blue'   },
  { name: 'Aisha Patel',    role: 'Data Scientist',          score: '82%', status: 'Under Review', badge: 'amber'  },
  { name: 'Carlos Rivera',  role: 'Frontend Developer',      score: '79%', status: 'Shortlisted',  badge: 'green'  },
  { name: 'Emma Williams',  role: 'Product Manager',         score: '75%', status: 'Applied',      badge: 'purple' },
  { name: 'James Okonkwo',  role: 'Cloud Architect',         score: '71%', status: 'Rejected',     badge: 'red'    },
];

export default function Recruitment() {
  return (
    <div className="module-page">

      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon blue" aria-hidden="true">🤖</div>
        <div>
          <h1>AI Recruitment</h1>
          <p>
            Automate resume screening, rank candidates by AI fit score,
            and manage your hiring pipeline end-to-end.
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

      {/* Candidate table */}
      <div className="content-panel">
        <h2>Recent Candidates — AI Ranked</h2>
        <table className="data-table" aria-label="Candidate list">
          <thead>
            <tr>
              <th>Candidate</th>
              <th>Role Applied</th>
              <th>AI Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {CANDIDATES.map((c) => (
              <tr key={c.name}>
                <td><strong>{c.name}</strong></td>
                <td>{c.role}</td>
                <td><strong>{c.score}</strong></td>
                <td>
                  <span className={`badge ${c.badge}`}>{c.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
