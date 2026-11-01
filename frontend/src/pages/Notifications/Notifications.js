/**
 * pages/Notifications/Notifications.js
 *
 * Full notification history. The topbar bell (layouts/AppLayout.js)
 * shows the recent/unread slice; this page is the "View all" landing:
 * filter by category, unread-only, mark one / a category / everything
 * read, and page back through older history.
 *
 * Admins and HR Managers also see the escalation log here — escalations
 * are delivered as notifications, so this is where they're followed up.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getMyNotifications, getUnreadCount, listEscalations, markAllNotificationsRead,
  markNotificationRead, runEscalationSweep,
} from '../../api/notificationsApi';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import { apiErrorText } from '../../utils/passwordPolicy';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './Notifications.css';

const PAGE_SIZE = 30;

export const CATEGORIES = [
  { key: '', label: 'All', icon: '🔔' },
  { key: 'sprint', label: 'Sprints', icon: '🏃' },
  { key: 'meeting', label: 'Meetings', icon: '🎙️' },
  { key: 'chat', label: 'Chat', icon: '💬' },
  { key: 'leave', label: 'Leave', icon: '🌴' },
  { key: 'project', label: 'Projects', icon: '📁' },
  { key: 'escalation', label: 'Escalations', icon: '⚠️' },
  { key: 'support', label: 'Support', icon: '🎧' },
  { key: 'general', label: 'General', icon: '📌' },
];

const CATEGORY_ICON = Object.fromEntries(CATEGORIES.map((c) => [c.key, c.icon]));
const ESCALATION_ROLES = ['admin', 'hr_manager'];
const RULE_LABEL = {
  leave_pending_overdue: 'Leave request waiting too long',
  action_items_unreviewed: 'Meeting action items unreviewed',
};

function currentRole() {
  if (process.env.REACT_APP_AUTH_DISABLED === 'true') return 'admin';
  try {
    return JSON.parse(localStorage.getItem('user'))?.role?.name?.toLowerCase() ?? '';
  } catch {
    return '';
  }
}

export default function Notifications() {
  const navigate = useNavigate();
  const role = currentRole();
  const canSeeEscalations = ESCALATION_ROLES.includes(role);

  const [category, setCategory] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [counts, setCounts] = useState({ total: 0, by_category: {} });
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');

  const [escalations, setEscalations] = useState([]);
  const [escalationFilter, setEscalationFilter] = useState('open');
  const [sweepNote, setSweepNote] = useState('');

  const loadCounts = useCallback(async () => {
    try { setCounts(await getUnreadCount()); } catch { /* badge only */ }
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await getMyNotifications({ category, unreadOnly, limit: PAGE_SIZE });
      setNotifications(data);
      setHasMore(data.length === PAGE_SIZE);
      setError('');
    } catch (err) {
      setError(apiErrorText(err, 'Could not load notifications.'));
    } finally {
      setLoading(false);
    }
    loadCounts();
  }, [category, unreadOnly, loadCounts]);

  useEffect(() => { setLoading(true); load(); }, [load]);

  const loadEscalations = useCallback(async () => {
    if (!canSeeEscalations) return;
    try {
      setEscalations(await listEscalations({ status: escalationFilter === 'all' ? undefined : escalationFilter }));
    } catch (err) {
      setError(apiErrorText(err, 'Could not load escalations.'));
    }
  }, [canSeeEscalations, escalationFilter]);

  useEffect(() => { loadEscalations(); }, [loadEscalations]);

  async function handleLoadMore() {
    if (!notifications.length) return;
    setLoadingMore(true);
    try {
      const older = await getMyNotifications({
        category, unreadOnly, limit: PAGE_SIZE, beforeId: notifications[notifications.length - 1].id,
      });
      setNotifications((list) => [...list, ...older]);
      setHasMore(older.length === PAGE_SIZE);
    } catch (err) {
      setError(apiErrorText(err, 'Could not load older notifications.'));
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleClick(n) {
    if (!n.read_at) {
      try { await markNotificationRead(n.id); } catch { /* non-fatal */ }
    }
    if (n.link) navigate(n.link);
    else load();
  }

  async function handleMarkAllRead() {
    try {
      await markAllNotificationsRead({ category });
      load();
    } catch (err) {
      setError(apiErrorText(err, 'Could not mark notifications read.'));
    }
  }

  async function handleRunSweep() {
    setSweepNote('');
    try {
      const result = await runEscalationSweep();
      setSweepNote(result.skipped
        ? result.reason
        : `Sweep finished — ${result.opened} opened, ${result.resolved} resolved.`);
      loadEscalations();
      load();
    } catch (err) {
      setError(apiErrorText(err, 'Could not run the escalation sweep.'));
    }
  }

  const unreadHere = category ? (counts.by_category[category] || 0) : counts.total;

  return (
    <div className="module-page notifications-page">
      <div className="module-page-header">
        <div className="module-page-icon amber" aria-hidden="true">🔔</div>
        <div>
          <h1>Notifications</h1>
          <p>Task assignments, messages, meetings, leave decisions and escalations — all in one place.</p>
        </div>
      </div>

      {error && <div className="alert error" role="alert">{error}</div>}

      <div className="content-panel">
        <div className="notif-toolbar">
          <div className="filter-chips" role="tablist" aria-label="Notification category">
            {CATEGORIES.map((c) => {
              const unread = c.key ? (counts.by_category[c.key] || 0) : counts.total;
              return (
                <button
                  key={c.key || 'all'}
                  type="button"
                  role="tab"
                  aria-selected={category === c.key}
                  className={`filter-chip${category === c.key ? ' active' : ''}`}
                  onClick={() => setCategory(c.key)}
                >
                  <span aria-hidden="true">{c.icon}</span> {c.label}
                  {unread > 0 && <span className="notif-chip-count">{unread}</span>}
                </button>
              );
            })}
          </div>
          <div className="notif-actions">
            <label className="notif-unread-toggle">
              <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
              Unread only
            </label>
            <button type="button" className="btn-secondary" onClick={handleMarkAllRead} disabled={unreadHere === 0}>
              Mark {category ? 'these' : 'all'} read
            </button>
          </div>
        </div>

        {loading ? (
          <LoadingSpinner label="Loading notifications…" />
        ) : notifications.length === 0 ? (
          <p className="muted-note">{unreadOnly ? 'You’re all caught up.' : 'No notifications here yet.'}</p>
        ) : (
          <ul className="notif-list">
            {notifications.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => handleClick(n)}
                  className={`notif-row${n.read_at ? '' : ' unread'}${n.category === 'escalation' ? ' escalation' : ''}`}
                >
                  <span className="notif-icon" aria-hidden="true">{CATEGORY_ICON[n.category] || '📌'}</span>
                  <span className="notif-body">
                    <span className="notif-message">{n.message}</span>
                    <small className="muted-note">
                      {new Date(n.created_at).toLocaleString()}
                      {n.category && ` · ${n.category}`}
                    </small>
                  </span>
                  {!n.read_at && <span className="notif-dot" aria-label="Unread" />}
                </button>
              </li>
            ))}
          </ul>
        )}
        {!loading && hasMore && (
          <div className="notif-more">
            <button type="button" className="btn-secondary" onClick={handleLoadMore} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load older'}
            </button>
          </div>
        )}
      </div>

      {canSeeEscalations && (
        <div className="content-panel">
          <div className="panel-header-row">
            <h2>Escalations</h2>
            <div className="notif-actions">
              <div className="filter-chips">
                {['open', 'resolved', 'all'].map((f) => (
                  <button key={f} type="button" className={`filter-chip${escalationFilter === f ? ' active' : ''}`}
                    aria-pressed={escalationFilter === f} onClick={() => setEscalationFilter(f)}>
                    {f}
                  </button>
                ))}
              </div>
              {role === 'admin' && (
                <button type="button" className="btn-secondary" onClick={handleRunSweep}>Run check now</button>
              )}
            </div>
          </div>
          <p className="muted-note">
            Raised automatically when a leave request or a meeting’s AI-proposed action items wait too long
            for a decision. Each one notifies the people who can act on it, once, and resolves itself when handled.
          </p>
          {sweepNote && <div className="alert info">{sweepNote}</div>}
          {escalations.length === 0 ? (
            <p className="muted-note">No {escalationFilter === 'all' ? '' : escalationFilter} escalations.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Rule</th><th>Details</th><th>Notified</th><th>Raised</th><th>Status</th></tr>
              </thead>
              <tbody>
                {escalations.map((e) => (
                  <tr key={e.id}>
                    <td>{RULE_LABEL[e.rule] || e.rule}</td>
                    <td>{e.summary}</td>
                    <td>{e.recipient_count}</td>
                    <td>{new Date(e.triggered_at).toLocaleString()}</td>
                    <td>
                      <span className={`badge ${e.status === 'open' ? 'amber' : 'green'}`}>{e.status}</span>
                      {e.resolved_at && <><br /><small className="muted-note">{new Date(e.resolved_at).toLocaleString()}</small></>}
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
