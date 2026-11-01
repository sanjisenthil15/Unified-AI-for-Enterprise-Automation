/**
 * pages/Leave/Leave.js
 *
 * Leave requests.
 *   - Any onboarded employee: request leave (type, dates, reason), see
 *     their own requests, cancel ones still pending.
 *   - Admin / HR Manager: an approval queue (approve, or reject with a
 *     required reason) and the full decision history.
 * Managers and team leads have no approval controls — the backend rejects
 * them too. Nobody can decide on their own request.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  approveLeaveRequest, cancelLeaveRequest, getLeaveTypes, getMyLeaveRequests,
  listLeaveRequests, rejectLeaveRequest, submitLeaveRequest,
} from '../../api/leaveApi';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import { apiErrorText } from '../../utils/passwordPolicy';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './Leave.css';

const APPROVER_ROLES = ['admin', 'hr_manager'];
const STATUS_BADGE = { pending: 'amber', approved: 'green', rejected: 'red', cancelled: 'purple' };
const HISTORY_FILTERS = ['all', 'pending', 'approved', 'rejected', 'cancelled'];
const EMPTY_FORM = { leaveType: 'annual', startDate: '', endDate: '', reason: '' };

function currentUser() {
  try {
    return JSON.parse(localStorage.getItem('user')) || null;
  } catch {
    return null;
  }
}

function label(value) {
  return (value || '').replace('_', ' ');
}

/** Mon–Fri days in [start, end] — same rule the backend uses. */
export function countWorkingDays(start, end) {
  if (!start || !end || end < start) return 0;
  let days = 0;
  const cur = new Date(`${start}T00:00:00`);
  const last = new Date(`${end}T00:00:00`);
  while (cur <= last) {
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) days += 1;
    cur.setDate(cur.getDate() + 1);
  }
  return days;
}

function DateRange({ req }) {
  return (
    <span>
      {req.start_date === req.end_date ? req.start_date : `${req.start_date} → ${req.end_date}`}
      <span className="muted-note"> · {req.working_days} working day{req.working_days === 1 ? '' : 's'}</span>
    </span>
  );
}

export default function Leave() {
  const [me] = useState(currentUser);
  const authDisabled = process.env.REACT_APP_AUTH_DISABLED === 'true';
  const role = authDisabled ? 'admin' : (me?.role?.name?.toLowerCase() ?? '');
  const isApprover = APPROVER_ROLES.includes(role);

  const [tab, setTab] = useState('mine');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyId, setBusyId] = useState(null);

  const [hasEmployeeRecord, setHasEmployeeRecord] = useState(true);
  const [leaveTypes, setLeaveTypes] = useState(['annual', 'sick', 'casual', 'unpaid', 'other']);
  const [mine, setMine] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const [queue, setQueue] = useState([]);
  const [history, setHistory] = useState([]);
  const [historyFilter, setHistoryFilter] = useState('all');
  const [rejecting, setRejecting] = useState(null); // request id whose reject form is open
  const [rejectReason, setRejectReason] = useState('');
  const [approveNotes, setApproveNotes] = useState({});

  const loadMine = useCallback(async () => {
    try {
      setMine(await getMyLeaveRequests());
      setHasEmployeeRecord(true);
    } catch (err) {
      if (err.response?.status === 404) setHasEmployeeRecord(false);
      else throw err;
    }
  }, []);

  const loadApprover = useCallback(async () => {
    if (!isApprover) return;
    const [pending, all] = await Promise.all([
      listLeaveRequests({ status: 'pending' }),
      listLeaveRequests({ status: historyFilter === 'all' ? undefined : historyFilter }),
    ]);
    setQueue(pending);
    setHistory(all);
  }, [isApprover, historyFilter]);

  const load = useCallback(async () => {
    try {
      const [types] = await Promise.all([
        getLeaveTypes().catch(() => null),
        loadMine(),
        loadApprover(),
      ]);
      if (types?.leave_types?.length) setLeaveTypes(types.leave_types);
      setError('');
    } catch (err) {
      setError(apiErrorText(err, 'Could not load leave requests.'));
    } finally {
      setLoading(false);
    }
  }, [loadMine, loadApprover]);

  useEffect(() => { load(); }, [load]);

  // Approvers without an employee record (e.g. the Admin) land on the queue.
  useEffect(() => {
    if (!loading && isApprover && !hasEmployeeRecord && tab === 'mine') setTab('queue');
  }, [loading, isApprover, hasEmployeeRecord, tab]);

  const workingDays = useMemo(() => countWorkingDays(form.startDate, form.endDate), [form.startDate, form.endDate]);
  const formError = form.startDate && form.endDate && form.endDate < form.startDate
    ? 'The end date must be on or after the start date.'
    : form.startDate && form.endDate && workingDays === 0
      ? 'Those dates contain no working days (Mon–Fri).'
      : '';

  function flash(text) {
    setNotice(text);
    setError('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (formError || form.reason.trim().length < 3) {
      setError(formError || 'Please give a reason (at least 3 characters).');
      return;
    }
    setSubmitting(true);
    setNotice('');
    try {
      await submitLeaveRequest({ ...form, reason: form.reason.trim() });
      setForm(EMPTY_FORM);
      await Promise.all([loadMine(), loadApprover()]);
      flash('Leave request submitted — HR will review it.');
    } catch (err) {
      setError(apiErrorText(err, 'Could not submit this leave request.'));
    } finally {
      setSubmitting(false);
    }
  }

  async function act(id, action, successText) {
    setBusyId(id);
    setNotice('');
    try {
      await action();
      await Promise.all([loadMine(), loadApprover()]);
      flash(successText);
      return true;
    } catch (err) {
      setError(apiErrorText(err, 'That action could not be completed.'));
      return false;
    } finally {
      setBusyId(null);
    }
  }

  async function handleCancel(req) {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Cancel your ${label(req.leave_type)} leave request (${req.start_date} → ${req.end_date})?`)) return;
    await act(req.id, () => cancelLeaveRequest(req.id), 'Leave request cancelled.');
  }

  async function handleApprove(req) {
    const ok = await act(req.id, () => approveLeaveRequest(req.id, approveNotes[req.id]?.trim()),
      `Approved ${req.employee.full_name}'s leave.`);
    if (ok) setApproveNotes((n) => ({ ...n, [req.id]: '' }));
  }

  async function handleReject(e, req) {
    e.preventDefault();
    if (rejectReason.trim().length < 3) {
      setError('A rejection reason is required (at least 3 characters).');
      return;
    }
    const ok = await act(req.id, () => rejectLeaveRequest(req.id, rejectReason.trim()),
      `Rejected ${req.employee.full_name}'s leave.`);
    if (ok) {
      setRejecting(null);
      setRejectReason('');
    }
  }

  const isOwn = (req) => me?.email && req.employee.email === me.email;

  return (
    <div className="module-page leave-page">
      <div className="module-page-header">
        <div className="module-page-icon green" aria-hidden="true">🌴</div>
        <div>
          <h1>Leave</h1>
          <p>{isApprover
            ? 'Request your own time off, and review the team’s leave requests.'
            : 'Request time off and follow its approval. Approved days are marked on leave in Attendance.'}</p>
        </div>
      </div>

      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert success" role="status">{notice}</div>}

      {isApprover && (
        <div className="tab-bar" role="tablist">
          {hasEmployeeRecord && (
            <button type="button" role="tab" aria-selected={tab === 'mine'}
              className={tab === 'mine' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('mine')}>
              My requests
            </button>
          )}
          <button type="button" role="tab" aria-selected={tab === 'queue'}
            className={tab === 'queue' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('queue')}>
            Approval queue{queue.length ? ` (${queue.length})` : ''}
          </button>
          <button type="button" role="tab" aria-selected={tab === 'history'}
            className={tab === 'history' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('history')}>
            History
          </button>
        </div>
      )}

      {loading && <LoadingSpinner label="Loading leave…" />}

      {!loading && tab === 'mine' && !hasEmployeeRecord && (
        <div className="content-panel">
          <p className="muted-note">No employee record yet — contact HR to be onboarded before requesting leave.</p>
        </div>
      )}

      {!loading && tab === 'mine' && hasEmployeeRecord && (
        <>
          <form className="content-panel leave-form" onSubmit={handleSubmit} aria-label="Request leave">
            <h2>Request leave</h2>
            <div className="form-grid">
              <div className="field-group">
                <label htmlFor="lv-type">Leave type</label>
                <select id="lv-type" className="field-select" value={form.leaveType}
                  onChange={(e) => setForm((f) => ({ ...f, leaveType: e.target.value }))}>
                  {leaveTypes.map((t) => <option key={t} value={t}>{label(t)}</option>)}
                </select>
              </div>
              <div className="field-group">
                <span className="leave-days-preview" aria-live="polite">
                  {form.startDate && form.endDate && !formError
                    ? `${workingDays} working day${workingDays === 1 ? '' : 's'}`
                    : 'Pick your dates'}
                </span>
              </div>
              <div className="field-group">
                <label htmlFor="lv-start">First day</label>
                <input id="lv-start" type="date" className="field-input" required value={form.startDate}
                  onChange={(e) => setForm((f) => ({ ...f, startDate: e.target.value }))} />
              </div>
              <div className="field-group">
                <label htmlFor="lv-end">Last day</label>
                <input id="lv-end" type="date" className="field-input" required value={form.endDate}
                  min={form.startDate || undefined}
                  onChange={(e) => setForm((f) => ({ ...f, endDate: e.target.value }))} />
              </div>
            </div>
            <div className="field-group">
              <label htmlFor="lv-reason">Reason</label>
              <textarea id="lv-reason" className="field-input" rows={2} maxLength={500} required value={form.reason}
                placeholder="Visible to HR and Admins only"
                onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
            </div>
            {formError && <p className="leave-form-error">{formError}</p>}
            <div className="leave-form-actions">
              <button type="submit" className="btn-primary" disabled={submitting || Boolean(formError)}>
                {submitting ? 'Submitting…' : 'Submit request'}
              </button>
            </div>
          </form>

          <div className="content-panel">
            <h2>My requests</h2>
            {mine.length === 0 ? (
              <p className="muted-note">You haven’t requested any leave yet.</p>
            ) : (
              <ul className="leave-list">
                {mine.map((req) => (
                  <li key={req.id} className="leave-item">
                    <div className="leave-item-main">
                      <div className="leave-item-top">
                        <strong>{label(req.leave_type)}</strong>
                        <span className={`badge ${STATUS_BADGE[req.status]}`}>{req.status}</span>
                      </div>
                      <DateRange req={req} />
                      <span className="muted-note leave-reason">{req.reason}</span>
                      {req.reviewed_by && (
                        <span className="muted-note">
                          {req.status === 'approved' ? 'Approved' : 'Rejected'} by {req.reviewed_by.full_name}
                          {req.decision_note ? ` — “${req.decision_note}”` : ''}
                        </span>
                      )}
                    </div>
                    {req.status === 'pending' && (
                      <button type="button" className="btn-secondary" disabled={busyId === req.id}
                        onClick={() => handleCancel(req)}>
                        Cancel request
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      {!loading && isApprover && tab === 'queue' && (
        <div className="content-panel">
          <h2>Waiting for a decision</h2>
          {queue.length === 0 ? (
            <p className="muted-note">Nothing to review — every request has been decided.</p>
          ) : (
            <ul className="leave-list">
              {queue.map((req) => (
                <li key={req.id} className="leave-item leave-item-review">
                  <div className="leave-item-main">
                    <div className="leave-item-top">
                      <strong>{req.employee.full_name}</strong>
                      <span className="muted-note">{req.employee.job_title}</span>
                      <span className="badge blue">{label(req.leave_type)}</span>
                    </div>
                    <DateRange req={req} />
                    <span className="leave-reason">{req.reason}</span>
                    <span className="muted-note">Requested {new Date(req.created_at).toLocaleString()}</span>
                  </div>
                  {isOwn(req) ? (
                    <span className="muted-note">Your own request — another approver must decide it.</span>
                  ) : rejecting === req.id ? (
                    <form className="leave-reject-form" onSubmit={(e) => handleReject(e, req)}>
                      <input className="field-input" autoFocus maxLength={500} aria-label="Rejection reason"
                        placeholder="Reason for rejecting (required)" value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)} />
                      <button type="submit" className="btn-primary leave-btn-reject" disabled={busyId === req.id}>
                        Confirm reject
                      </button>
                      <button type="button" className="btn-secondary" onClick={() => { setRejecting(null); setRejectReason(''); }}>
                        Back
                      </button>
                    </form>
                  ) : (
                    <div className="leave-review-actions">
                      <input className="field-input" maxLength={500} aria-label="Approval note (optional)"
                        placeholder="Note (optional)" value={approveNotes[req.id] || ''}
                        onChange={(e) => setApproveNotes((n) => ({ ...n, [req.id]: e.target.value }))} />
                      <button type="button" className="btn-primary" disabled={busyId === req.id} onClick={() => handleApprove(req)}>
                        Approve
                      </button>
                      <button type="button" className="btn-secondary leave-btn-reject" disabled={busyId === req.id}
                        onClick={() => { setRejecting(req.id); setRejectReason(''); }}>
                        Reject…
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!loading && isApprover && tab === 'history' && (
        <div className="content-panel">
          <div className="panel-header-row">
            <h2>All requests</h2>
            <div className="filter-chips">
              {HISTORY_FILTERS.map((f) => (
                <button key={f} type="button" className={`filter-chip${historyFilter === f ? ' active' : ''}`}
                  aria-pressed={historyFilter === f} onClick={() => setHistoryFilter(f)}>
                  {f}
                </button>
              ))}
            </div>
          </div>
          {history.length === 0 ? (
            <p className="muted-note">No requests match this filter.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Employee</th><th>Type</th><th>Dates</th><th>Status</th><th>Decision</th></tr>
              </thead>
              <tbody>
                {history.map((req) => (
                  <tr key={req.id}>
                    <td>{req.employee.full_name}<br /><small className="muted-note">{req.employee.employee_code}</small></td>
                    <td>{label(req.leave_type)}</td>
                    <td><DateRange req={req} /></td>
                    <td><span className={`badge ${STATUS_BADGE[req.status]}`}>{req.status}</span></td>
                    <td>
                      {req.reviewed_by
                        ? <>{req.reviewed_by.full_name}<br /><small className="muted-note">{req.decision_note || '—'}</small></>
                        : req.status === 'cancelled' ? <small className="muted-note">Cancelled by employee</small> : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
