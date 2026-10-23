/**
 * pages/Notifications/Notifications.js
 *
 * Full notification history. The topbar bell (layouts/AppLayout.js)
 * shows the recent/unread slice; this page is the "View all" landing.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMyNotifications, markAllNotificationsRead, markNotificationRead } from '../../api/notificationsApi';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';

export default function Notifications() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await getMyNotifications();
      setNotifications(data);
      setError('');
    } catch {
      setError('Could not load notifications.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleClick(n) {
    if (!n.read_at) {
      try { await markNotificationRead(n.id); } catch { /* non-fatal */ }
    }
    if (n.link) navigate(n.link);
    load();
  }

  async function handleMarkAllRead() {
    try {
      await markAllNotificationsRead();
      load();
    } catch {
      setError('Could not mark notifications read.');
    }
  }

  return (
    <div className="module-page">
      <div className="module-page-header">
        <div className="module-page-icon amber" aria-hidden="true">🔔</div>
        <div><h1>Notifications</h1><p>Task assignments, messages, and sprint updates.</p></div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="content-panel">
        <div className="panel-header-row">
          <h2>All notifications</h2>
          <button className="btn-secondary" onClick={handleMarkAllRead}>Mark all read</button>
        </div>

        {loading ? (
          <p>Loading…</p>
        ) : notifications.length === 0 ? (
          <p className="muted-note">No notifications yet.</p>
        ) : (
          <div>
            {notifications.map((n) => (
              <div
                key={n.id}
                onClick={() => handleClick(n)}
                className={`notification-row${n.read_at ? '' : ' unread'}`}
              >
                <div>{n.message}</div>
                <small className="muted-note">{new Date(n.created_at).toLocaleString()}</small>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
