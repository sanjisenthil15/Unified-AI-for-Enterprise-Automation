/**
 * modules/meetingIntelligence/MeetingList.js
 *
 * Meeting history table. Click a row to open the meeting details.
 */

import React from 'react';
import { formatDate, formatDuration, statusBadge } from './helpers';

export default function MeetingList({ meetings, loading, selectedId, onSelect }) {
  if (loading && (!meetings || meetings.length === 0)) {
    return <div className="mi-muted">Loading meeting history…</div>;
  }
  if (!meetings || meetings.length === 0) {
    return <div className="mi-empty">No meetings yet. Upload a recording to get started.</div>;
  }

  return (
    <table className="data-table mi-table" aria-label="Meeting history">
      <thead>
        <tr>
          <th>Title</th>
          <th>Meeting date</th>
          <th>Duration</th>
          <th>Status</th>
          <th aria-hidden="true" />
        </tr>
      </thead>
      <tbody>
        {meetings.map((m) => {
          const { label, badge } = statusBadge(m.status);
          return (
            <tr
              key={m.id}
              className={`mi-row${selectedId === m.id ? ' mi-row-active' : ''}`}
              onClick={() => onSelect(m.id)}
              tabIndex={0}
              role="button"
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(m.id)}
            >
              <td><strong>{m.title}</strong></td>
              <td>{formatDate(m.meeting_date || m.created_at)}</td>
              <td>{formatDuration(m.duration_sec)}</td>
              <td><span className={`badge ${badge}`}>{label}</span></td>
              <td className="mi-row-open">View →</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
