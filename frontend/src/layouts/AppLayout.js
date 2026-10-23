/**
 * layouts/AppLayout.js
 *
 * Shared layout shell — sidebar + topbar + <Outlet>.
 *
 * Role-based sidebar: each item's `roles` (null = everyone) decides
 * whether it's shown for the current user's role. This only hides the
 * link — real enforcement for role-sensitive pages lives in App.js's
 * ProtectedRoute(allowedRoles=...).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { getMyNotifications, markNotificationRead } from '../api/notificationsApi';
import './AppLayout.css';

const NOTIFICATION_POLL_MS = 20000;

const NAV_ITEMS = [
  { to: '/dashboard',        icon: '🏠', label: 'Dashboard',            roles: null },
  { to: '/hr',                icon: '🧑‍💼', label: 'HR Recruitment',     roles: null },
  { to: '/customer-support',  icon: '🎧', label: 'Customer Support',    roles: null },
  { to: '/incidents',         icon: '🚨', label: 'Incident Management', roles: null },
  { to: '/meetings',          icon: '🎙️', label: 'Meetings',            roles: null },
  { to: '/employees',         icon: '👥', label: 'Employee Management', roles: ['admin', 'hr_manager'] },
  { to: '/attendance',        icon: '🕒', label: 'Attendance',          roles: null },
  { to: '/sprints',           icon: '🏃', label: 'Sprints',             roles: null },
  { to: '/chat',              icon: '💬', label: 'Team Chat',           roles: null },
  { to: '/analytics',         icon: '📊', label: 'Analytics',           roles: null },
  { to: '/profile',           icon: '👤', label: 'My Profile',          roles: null },
];

export default function AppLayout() {
  const navigate = useNavigate();

  const [user] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user')) || null; }
    catch { return null; }
  });

  // AUTH_DISABLED means the backend treats every request as the seeded
  // admin — match that here so dev mode doesn't hide admin-only links.
  const authDisabled = process.env.REACT_APP_AUTH_DISABLED === 'true';
  const role         = authDisabled ? 'admin' : (user?.role?.name?.toLowerCase() ?? '');
  const displayName  = user?.full_name  ?? (authDisabled ? 'Demo Admin' : 'User');
  const displayRole  = user?.role?.name ?? (authDisabled ? 'admin' : '');
  const avatarLetter = displayName.charAt(0).toUpperCase();

  const navItems = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));

  const [notifications, setNotifications] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const unreadCount = notifications.filter((n) => !n.read_at).length;

  const loadNotifications = useCallback(() => {
    getMyNotifications().then(setNotifications).catch(() => {});
  }, []);

  useEffect(() => {
    loadNotifications();
    const t = setInterval(loadNotifications, NOTIFICATION_POLL_MS);
    return () => clearInterval(t);
  }, [loadNotifications]);

  async function handleNotificationClick(n) {
    if (!n.read_at) {
      try { await markNotificationRead(n.id); } catch { /* non-fatal */ }
    }
    setShowNotifications(false);
    loadNotifications();
    if (n.link) navigate(n.link);
  }

  function handleLogout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    navigate('/login');
  }

  return (
    <div className="app-layout">

      <aside className="sidebar" aria-label="Sidebar navigation">
        <div className="sidebar-brand">
          <span className="sidebar-brand-icon" aria-hidden="true">⚡</span>
          <span className="sidebar-brand-name">
            Unified <span>AI</span><br />Enterprise
          </span>
        </div>

        <nav className="sidebar-nav" aria-label="Module navigation">
          <span className="sidebar-section-label">Navigation</span>
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              aria-label={item.label}
            >
              <span className="sidebar-link-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="sidebar-logout" onClick={handleLogout} aria-label="Logout">
            <span className="sidebar-link-icon" aria-hidden="true">🚪</span>
            Logout
          </button>
        </div>
      </aside>

      <div className="layout-body">
        <header className="layout-topbar" aria-label="Top navigation">
          <span className="topbar-page-title">Unified AI Enterprise Platform</span>
          <div className="topbar-right">
            <div className="topbar-notifications">
              <button
                className="topbar-bell"
                aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
                onClick={() => setShowNotifications((v) => !v)}
              >
                🔔
                {unreadCount > 0 && <span className="topbar-bell-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>}
              </button>
              {showNotifications && (
                <div className="topbar-notifications-dropdown">
                  {notifications.length === 0 ? (
                    <p className="topbar-notifications-empty">No notifications yet.</p>
                  ) : (
                    notifications.slice(0, 8).map((n) => (
                      <div
                        key={n.id}
                        className={`topbar-notification-item${n.read_at ? '' : ' unread'}`}
                        onClick={() => handleNotificationClick(n)}
                      >
                        {n.message}
                      </div>
                    ))
                  )}
                  <NavLink to="/notifications" className="topbar-notifications-viewall" onClick={() => setShowNotifications(false)}>
                    View all
                  </NavLink>
                </div>
              )}
            </div>
            <span className="topbar-badge">{displayRole}</span>
            <div className="topbar-avatar" title={displayName}
              aria-label={`Logged in as ${displayName}`} role="img">
              {avatarLetter}
            </div>
          </div>
        </header>

        <main className="layout-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
