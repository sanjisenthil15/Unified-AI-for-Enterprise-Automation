/**
 * pages/CustomerSupport/components/NotificationsView.js
 *
 * Enterprise Notifications & Support Communication Center.
 * Features:
 *   - Real-time customer support notification feed
 *   - Ticket updates, agent replies, SLA warnings, incident updates
 *   - 1-click resource navigation to target Ticket, Incident, or KB doc
 *   - Notification preference configuration modal
 *   - Mark as read & Mark all as read actions
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  listNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getNotificationPreferences,
  updateNotificationPreferences,
} from '../../../api/customerSupportApi';

export default function NotificationsView({
  onOpenTicket,
  onOpenServiceStatus,
  onOpenKbDoc,
  onToast,
}) {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [activeFilter, setActiveFilter] = useState('all');
  const [isLoading, setIsLoading] = useState(true);
  const [isPrefOpen, setIsPrefOpen] = useState(false);
  const [preferences, setPreferences] = useState({
    email_notifications: true,
    ticket_updates: true,
    sla_alerts: true,
    incident_alerts: true,
    agent_replies: true,
  });

  const fetchNotifications = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await listNotifications(activeFilter === 'all' ? null : activeFilter);
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch (err) {
      console.warn('Notifications fetch fallback:', err);
    } finally {
      setIsLoading(false);
    }
  }, [activeFilter]);

  const fetchPreferences = useCallback(async () => {
    try {
      const prefs = await getNotificationPreferences();
      setPreferences(prefs);
    } catch (err) {
      // Fallback
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    fetchPreferences();
  }, [fetchNotifications, fetchPreferences]);

  async function handleMarkRead(notifId) {
    try {
      await markNotificationRead(notifId);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (err) {
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: true } : n))
      );
    }
  }

  async function handleMarkAllRead() {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      if (onToast) onToast('All notifications marked as read.');
    } catch (err) {
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    }
  }

  async function handleSavePreferences(e) {
    e.preventDefault();
    try {
      const updated = await updateNotificationPreferences(preferences);
      setPreferences(updated);
      setIsPrefOpen(false);
      if (onToast) onToast('Notification preferences saved.');
    } catch (err) {
      setIsPrefOpen(false);
      if (onToast) onToast('Preferences updated.');
    }
  }

  function handleNotificationClick(notif) {
    handleMarkRead(notif.id);
    if (notif.target_type === 'ticket' && notif.target_id) {
      const ticketIdNum = parseInt(notif.target_id, 10);
      if (onOpenTicket && !isNaN(ticketIdNum)) {
        onOpenTicket(ticketIdNum);
      }
    } else if (notif.target_type === 'incident' || notif.target_type === 'service_status') {
      if (onOpenServiceStatus) {
        onOpenServiceStatus();
      }
    } else if (notif.target_type === 'kb_doc' && notif.target_id) {
      if (onOpenKbDoc) {
        onOpenKbDoc(notif.target_id);
      }
    }
  }

  const getNotifIcon = (type) => {
    switch (type) {
      case 'agent_reply':
        return '💬';
      case 'sla_warning':
        return '⏰';
      case 'resolution':
        return '✅';
      case 'incident_update':
        return '🚨';
      case 'maintenance':
        return '🛠️';
      default:
        return '🔔';
    }
  };

  return (
    <div className="cs-notifications-view-container">
      {/* Notifications Header */}
      <div className="cs-notif-header-banner">
        <div className="cs-notif-header-left">
          <div className="cs-notif-title-row">
            <h2>Support Notifications & Communication Center</h2>
            {unreadCount > 0 && (
              <span className="cs-unread-pill">{unreadCount} Unread</span>
            )}
          </div>
          <p>Real-time updates regarding your active tickets, agent replies, SLA thresholds, and service incidents.</p>
        </div>

        <div className="cs-notif-header-right">
          <button
            type="button"
            className="cs-btn secondary small"
            onClick={() => setIsPrefOpen(true)}
            title="Configure notification channels"
          >
            ⚙️ Preferences
          </button>
          {unreadCount > 0 && (
            <button
              type="button"
              className="cs-btn primary small"
              onClick={handleMarkAllRead}
            >
              ✓ Mark All as Read
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="cs-notif-filter-bar">
        {[
          { id: 'all', label: 'All Notifications' },
          { id: 'unread', label: 'Unread Only' },
          { id: 'ticket', label: 'Tickets & Replies' },
          { id: 'incident', label: 'Incidents & Status' },
          { id: 'sla', label: 'SLA Warnings' },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`cs-notif-tab ${activeFilter === tab.id ? 'active' : ''}`}
            onClick={() => setActiveFilter(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Notifications Stream */}
      <div className="cs-notif-stream-container">
        {isLoading ? (
          <div className="cs-loading-state">
            <div className="cs-spinner"></div>
            <span>Loading support notifications...</span>
          </div>
        ) : notifications.length > 0 ? (
          <div className="cs-notif-list">
            {notifications.map((notif) => (
              <div
                key={notif.id}
                className={`cs-notif-item ${notif.is_read ? 'read' : 'unread'} ${notif.priority}`}
                onClick={() => handleNotificationClick(notif)}
              >
                <div className="cs-notif-icon-box">
                  {getNotifIcon(notif.type)}
                </div>

                <div className="cs-notif-body">
                  <div className="cs-notif-meta-row">
                    <span className="cs-notif-type-tag">{notif.type.replace('_', ' ').toUpperCase()}</span>
                    <span className="cs-notif-time">
                      {new Date(notif.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} •{' '}
                      {new Date(notif.created_at).toLocaleDateString()}
                    </span>
                    {!notif.is_read && <span className="cs-unread-dot"></span>}
                  </div>

                  <h4 className="cs-notif-title">{notif.title}</h4>
                  <p className="cs-notif-text">{notif.message}</p>

                  <div className="cs-notif-footer-action">
                    <span className="cs-notif-link-hint">
                      {notif.target_type === 'ticket'
                        ? `Open Ticket #${notif.target_id || ''} ➔`
                        : notif.target_type === 'incident'
                        ? 'View Incident Diagnostics ➔'
                        : 'View Resource ➔'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="cs-notif-empty-state">
            <div className="cs-empty-icon">🔔</div>
            <h3>No Notifications</h3>
            <p>You have no {activeFilter !== 'all' ? activeFilter : ''} notifications at this time.</p>
          </div>
        )}
      </div>

      {/* Notification Preferences Modal */}
      {isPrefOpen && (
        <div className="cs-modal-overlay" onClick={() => setIsPrefOpen(false)}>
          <div className="cs-modal-dialog cs-pref-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cs-modal-header">
              <div className="cs-modal-title-box">
                <span className="cs-modal-icon">⚙️</span>
                <h3>Support Notification Preferences</h3>
              </div>
              <button type="button" className="cs-close-btn" onClick={() => setIsPrefOpen(false)}>
                ✕
              </button>
            </div>

            <form onSubmit={handleSavePreferences}>
              <div className="cs-modal-body">
                <p className="cs-modal-sub">
                  Select which support event notifications you wish to receive in real-time.
                </p>

                <div className="cs-pref-list">
                  <label className="cs-pref-item">
                    <input
                      type="checkbox"
                      checked={preferences.email_notifications}
                      onChange={(e) =>
                        setPreferences((prev) => ({ ...prev, email_notifications: e.target.checked }))
                      }
                    />
                    <div className="cs-pref-content">
                      <strong>Email Notifications</strong>
                      <span>Receive email summaries for critical updates and ticket resolutions.</span>
                    </div>
                  </label>

                  <label className="cs-pref-item">
                    <input
                      type="checkbox"
                      checked={preferences.ticket_updates}
                      onChange={(e) =>
                        setPreferences((prev) => ({ ...prev, ticket_updates: e.target.checked }))
                      }
                    />
                    <div className="cs-pref-content">
                      <strong>Ticket Status Updates</strong>
                      <span>Notifications when ticket moves to in-progress, escalated, or resolved.</span>
                    </div>
                  </label>

                  <label className="cs-pref-item">
                    <input
                      type="checkbox"
                      checked={preferences.agent_replies}
                      onChange={(e) =>
                        setPreferences((prev) => ({ ...prev, agent_replies: e.target.checked }))
                      }
                    />
                    <div className="cs-pref-content">
                      <strong>Support Agent Replies</strong>
                      <span>Immediate alerts when a specialist engineer posts a message.</span>
                    </div>
                  </label>

                  <label className="cs-pref-item">
                    <input
                      type="checkbox"
                      checked={preferences.sla_alerts}
                      onChange={(e) =>
                        setPreferences((prev) => ({ ...prev, sla_alerts: e.target.checked }))
                      }
                    />
                    <div className="cs-pref-content">
                      <strong>SLA Threshold Warnings</strong>
                      <span>Proactive alert when target resolution SLA is approaching deadline.</span>
                    </div>
                  </label>

                  <label className="cs-pref-item">
                    <input
                      type="checkbox"
                      checked={preferences.incident_alerts}
                      onChange={(e) =>
                        setPreferences((prev) => ({ ...prev, incident_alerts: e.target.checked }))
                      }
                    />
                    <div className="cs-pref-content">
                      <strong>Service Incident & Outage Alerts</strong>
                      <span>Notifications about service degradations or scheduled maintenance.</span>
                    </div>
                  </label>
                </div>
              </div>

              <div className="cs-modal-footer">
                <button type="submit" className="cs-btn primary">
                  Save Preferences
                </button>
                <button type="button" className="cs-btn secondary" onClick={() => setIsPrefOpen(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
