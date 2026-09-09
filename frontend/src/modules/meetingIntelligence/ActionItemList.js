/**
 * modules/meetingIntelligence/ActionItemList.js
 *
 * AI-extracted action items. Read-only for now: the backend has no
 * assignment endpoint yet, so "Assign" is disabled. The data model already
 * supports manual assignment (assigned_to_user_id / assignment_method /
 * due_date) — only the PATCH route is missing.
 */

import React from 'react';
import { formatDate } from './helpers';

const ITEM_STATUS_BADGE = {
  pending: 'purple',
  in_progress: 'blue',
  completed: 'green',
  cancelled: 'red',
};

export default function ActionItemList({ items = [] }) {
  return (
    <section className="content-panel mi-panel">
      <h2>Action Items <span className="mi-count">{items.length}</span></h2>

      {items.length === 0 ? (
        <p className="mi-muted">No action items were extracted from this meeting.</p>
      ) : (
        <ul className="mi-action-items">
          {items.map((it) => {
            const badge = ITEM_STATUS_BADGE[it.status] || 'purple';
            const assignee =
              it.assigned_to_user_id
                ? `User #${it.assigned_to_user_id}`
                : it.assigned_to_employee_id
                ? `Employee #${it.assigned_to_employee_id}`
                : it.assignee_name_raw
                ? `${it.assignee_name_raw} (from transcript)`
                : 'Unassigned';

            return (
              <li key={it.id} className="mi-action-item">
                <div className="mi-action-main">
                  <span className={`badge ${badge}`}>{it.status.replace('_', ' ')}</span>
                  <span className="mi-action-desc">{it.description}</span>
                </div>
                <div className="mi-action-meta">
                  <span>👤 {assignee}</span>
                  {it.due_date && <span>📅 {formatDate(it.due_date)}</span>}
                  {it.priority && <span>⚑ {it.priority}</span>}
                  {it.ai_confidence != null && (
                    <span title="AI confidence this was an action item">
                      🤖 {Math.round(it.ai_confidence * 100)}%
                    </span>
                  )}
                  <button
                    type="button"
                    className="mi-btn mi-btn-ghost mi-btn-sm"
                    disabled
                    title="Manual assignment is coming — the backend endpoint is not built yet."
                  >
                    Assign person
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
