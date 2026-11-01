/**
 * pages/AuditLog/AuditLog.js
 *
 * Admin-only, read-only view of the audit trail: who changed what, when,
 * and the before/after values. Rows can't be edited or removed — there is
 * no API for it and the database rejects it. Requests that share a
 * correlation id were one HTTP call; click it to see everything that call did.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { listAuditLogs } from '../../api/auditApi';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import { apiErrorText } from '../../utils/passwordPolicy';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './AuditLog.css';

const PAGE_SIZE = 50;
const ENTITY_TYPES = [
  ['', 'All records'],
  ['project', 'Projects'],
  ['employee', 'Employees'],
  ['user', 'User accounts'],
  ['leave_request', 'Leave requests'],
  ['meeting_action_item', 'Meeting action items'],
  ['escalation', 'Escalations'],
];
const EMPTY_FILTERS = { entityType: '', entityId: '', action: '', correlationId: '', occurredFrom: '', occurredTo: '' };

/** Date inputs are local calendar days; the API takes instants. */
function toQuery(f) {
  return {
    ...f,
    occurredFrom: f.occurredFrom ? new Date(`${f.occurredFrom}T00:00:00`).toISOString() : '',
    occurredTo: f.occurredTo ? new Date(`${f.occurredTo}T23:59:59`).toISOString() : '',
  };
}

function formatValue(value) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  return String(value);
}

function Changes({ before, after }) {
  const keys = Array.from(new Set([...Object.keys(before || {}), ...Object.keys(after || {})]));
  if (!keys.length) return <span className="muted-note">—</span>;
  return (
    <dl className="audit-changes">
      {keys.map((k) => (
        <div key={k} className="audit-change">
          <dt>{k.replace(/_/g, ' ')}</dt>
          <dd>
            {before && k in before && <span className="audit-before">{formatValue(before[k])}</span>}
            {before && k in before && after && k in after && <span aria-hidden="true"> → </span>}
            {after && k in after && <span className="audit-after">{formatValue(after[k])}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function AuditLog() {
  const [draft, setDraft] = useState(EMPTY_FILTERS);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [items, setItems] = useState([]);
  const [nextBeforeId, setNextBeforeId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = await listAuditLogs({ ...toQuery(filters), limit: PAGE_SIZE });
      setItems(page.items);
      setNextBeforeId(page.next_before_id);
      setError('');
    } catch (err) {
      setError(apiErrorText(err, 'Could not load the audit log.'));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  async function handleMore() {
    setLoadingMore(true);
    try {
      const page = await listAuditLogs({ ...toQuery(filters), beforeId: nextBeforeId, limit: PAGE_SIZE });
      setItems((list) => [...list, ...page.items]);
      setNextBeforeId(page.next_before_id);
    } catch (err) {
      setError(apiErrorText(err, 'Could not load older entries.'));
    } finally {
      setLoadingMore(false);
    }
  }

  function apply(e) {
    e.preventDefault();
    setFilters({ ...draft, entityId: draft.entityId.trim(), action: draft.action.trim(), correlationId: draft.correlationId.trim() });
  }

  function showCorrelation(id) {
    const next = { ...EMPTY_FILTERS, correlationId: id };
    setDraft(next);
    setFilters(next);
  }

  function showEntity(type, id) {
    const next = { ...EMPTY_FILTERS, entityType: type, entityId: id || '' };
    setDraft(next);
    setFilters(next);
  }

  const field = (name) => ({
    value: draft[name],
    onChange: (e) => setDraft((d) => ({ ...d, [name]: e.target.value })),
  });

  return (
    <div className="module-page audit-page">
      <div className="module-page-header">
        <div className="module-page-icon red" aria-hidden="true">🛡️</div>
        <div>
          <h1>Audit Log</h1>
          <p>An append-only record of who changed what. Passwords, tokens and private notes are never recorded.</p>
        </div>
      </div>

      {error && <div className="alert error" role="alert">{error}</div>}

      <form className="content-panel audit-filters" onSubmit={apply} aria-label="Filter audit log">
        <div className="field-group">
          <label htmlFor="au-type">Record type</label>
          <select id="au-type" className="field-select" {...field('entityType')}>
            {ENTITY_TYPES.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        </div>
        <div className="field-group">
          <label htmlFor="au-id">Record id</label>
          <input id="au-id" className="field-input" placeholder="e.g. 12" {...field('entityId')} />
        </div>
        <div className="field-group">
          <label htmlFor="au-action">Action</label>
          <input id="au-action" className="field-input" placeholder="e.g. leave_request. or auth.login_failed" {...field('action')} />
        </div>
        <div className="field-group">
          <label htmlFor="au-from">From</label>
          <input id="au-from" type="date" className="field-input" {...field('occurredFrom')} />
        </div>
        <div className="field-group">
          <label htmlFor="au-to">To</label>
          <input id="au-to" type="date" className="field-input" {...field('occurredTo')} />
        </div>
        <div className="field-group">
          <label htmlFor="au-corr">Correlation id</label>
          <input id="au-corr" className="field-input" {...field('correlationId')} />
        </div>
        <div className="audit-filter-actions">
          <button type="submit" className="btn-primary">Apply</button>
          <button type="button" className="btn-secondary" onClick={() => { setDraft(EMPTY_FILTERS); setFilters(EMPTY_FILTERS); }}>
            Reset
          </button>
        </div>
      </form>

      <div className="content-panel">
        {loading ? (
          <LoadingSpinner label="Loading audit log…" />
        ) : items.length === 0 ? (
          <p className="muted-note">No audit entries match these filters.</p>
        ) : (
          <div className="audit-table-wrap">
            <table className="data-table audit-table">
              <thead>
                <tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Changes</th><th>Request</th></tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id}>
                    <td className="audit-when">{new Date(row.occurred_at).toLocaleString()}</td>
                    <td>
                      {row.actor_name || (row.actor_user_id ? `User #${row.actor_user_id}` : <span className="muted-note">System / anonymous</span>)}
                      {row.actor_role && <><br /><small className="muted-note">{row.actor_role}</small></>}
                    </td>
                    <td><code className="audit-action">{row.action}</code></td>
                    <td>
                      <button type="button" className="btn-link" onClick={() => showEntity(row.entity_type, row.entity_id)}>
                        {row.entity_type.replace(/_/g, ' ')}{row.entity_id ? ` #${row.entity_id}` : ''}
                      </button>
                    </td>
                    <td><Changes before={row.before} after={row.after} /></td>
                    <td>
                      {row.correlation_id ? (
                        <button type="button" className="btn-link audit-corr" title={row.correlation_id}
                          onClick={() => showCorrelation(row.correlation_id)}>
                          {row.correlation_id.slice(0, 8)}…
                        </button>
                      ) : <span className="muted-note">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && nextBeforeId && (
          <div className="audit-more">
            <button type="button" className="btn-secondary" onClick={handleMore} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load older entries'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
