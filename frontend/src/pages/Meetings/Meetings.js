/**
 * pages/Meetings/Meetings.js
 *
 * Static presentation page for the Meeting Intelligence module.
 * No API calls — all data is hard-coded for demo purposes.
 */

import React from 'react';
import '../Recruitment/Recruitment.css';   // reuse shared module-page styles

const STATS = [
  { label: 'Meetings This Week', value: '17',   note: '3 pending transcription' },
  { label: 'Transcribed',        value: '14',   note: 'Whisper AI' },
  { label: 'Summaries Generated',value: '14',   note: 'Gemini AI' },
  { label: 'Action Items',       value: '62',   note: '18 overdue' },
];

const MEETINGS = [
  { title: 'Q3 Product Roadmap Review',     date: '2024-07-15', duration: '52 min', status: 'Completed',   badge: 'green',  items: 8  },
  { title: 'Sprint 24 Retrospective',       date: '2024-07-14', duration: '38 min', status: 'Completed',   badge: 'green',  items: 5  },
  { title: 'Investor Update Call',          date: '2024-07-14', duration: '1h 10m', status: 'Completed',   badge: 'green',  items: 3  },
  { title: 'Security Architecture Review',  date: '2024-07-13', duration: '45 min', status: 'Summarising', badge: 'blue',   items: 0  },
  { title: 'Customer Onboarding Workshop',  date: '2024-07-12', duration: '2h 05m', status: 'Transcribing',badge: 'amber',  items: 0  },
  { title: 'Weekly All-Hands',              date: '2024-07-11', duration: '28 min', status: 'Pending',     badge: 'purple', items: 0  },
];

export default function Meetings() {
  return (
    <div className="module-page">

      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon cyan" aria-hidden="true">🎙️</div>
        <div>
          <h1>Meeting Intelligence</h1>
          <p>
            Upload audio recordings and get Whisper transcriptions, Gemini
            summaries, and AI-extracted action items instantly.
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

      {/* Meetings table */}
      <div className="content-panel">
        <h2>Recent Meetings</h2>
        <table className="data-table" aria-label="Meeting list">
          <thead>
            <tr>
              <th>Title</th>
              <th>Date</th>
              <th>Duration</th>
              <th>Status</th>
              <th>Action Items</th>
            </tr>
          </thead>
          <tbody>
            {MEETINGS.map((m) => (
              <tr key={m.title}>
                <td><strong>{m.title}</strong></td>
                <td>{m.date}</td>
                <td>{m.duration}</td>
                <td>
                  <span className={`badge ${m.badge}`}>{m.status}</span>
                </td>
                <td>
                  {m.items > 0
                    ? <span className="badge blue">{m.items} items</span>
                    : <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>—</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
