/**
 * layouts/AppLayout.js
 *
 * Shared layout shell — slim icon sidebar + topbar + <Outlet>.
 *
 * Role-based sidebar: each item's `roles` (null = everyone) decides
 * whether it's shown for the current user's role. This only hides the
 * link — real enforcement for role-sensitive pages lives in App.js's
 * ProtectedRoute(allowedRoles=...).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { getMyNotifications, markNotificationRead } from '../api/notificationsApi';
import Avatar from '../components/common/Avatar';
import './AppLayout.css';

const NOTIFICATION_POLL_MS = 20000;
const SIDEBAR_PREF_KEY = 'sidebar_expanded';

const NAV_ITEMS = [
  { to: '/dashboard',        icon: '🏠', label: 'Dashboard',            roles: null },
  { to: '/hr',                icon: '🧑‍💼', label: 'HR Recruitment',     roles: ['admin', 'hr_manager', 'recruiter'] },
  { to: '/customer-support',  icon: '🎧', label: 'Customer Support',    roles: null },
  { to: '/incidents',         icon: '🚨', label: 'Incident Management', roles: null },
  { to: '/meetings',          icon: '🎙️', label: 'Meetings',            roles: null },
  { to: '/employees',         icon: '👥', label: 'Employee Management', roles: ['admin', 'hr_manager'] },
  { to: '/attendance',        icon: '🕒', label: 'Attendance',          roles: null },
  { to: '/sprints',           icon: '🏃', label: 'Sprints',             roles: null },
  { to: '/chat',              icon: '💬', label: 'Team Chat',           roles: null },
  { to: '/profile',           icon: '👤', label: 'My Profile',          roles: null },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

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
  const displayEmail = user?.email ?? '';

  const navItems = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(role));

  const [expanded, setExpanded] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_PREF_KEY) === '1'; } catch { return false; }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  function toggleExpanded() {
    setExpanded((v) => {
      const next = !v;
      try { localStorage.setItem(SIDEBAR_PREF_KEY, next ? '1' : '0'); } catch { /* ignore */ }
      return next;
    });
  }

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

  // On mobile the sidebar is an overlay that's either hidden or fully
  // open — there's no separate collapsed rail state there, so it always
  // shows labels while open regardless of the desktop expand/collapse
  // preference.
  const showLabels = expanded || mobileOpen;

  return (
    <div className={`app-layout${expanded ? ' is-expanded' : ''}`}>

      <aside
        className={`sidebar${expanded ? ' is-expanded' : ''}${mobileOpen ? ' is-mobile-open' : ''}`}
        aria-label="Sidebar navigation"
      >
        <div className="sidebar-brand">
          <span className="sidebar-brand-mark" aria-hidden="true">⚡</span>
          {showLabels && <span className="sidebar-brand-name">EnterpriseAI</span>}
          <button
            type="button"
            className="sidebar-collapse-toggle"
            onClick={toggleExpanded}
            aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
            title={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {expanded ? '«' : '»'}
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Module navigation">
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              aria-label={item.label}
              title={showLabels ? undefined : item.label}
              onClick={() => setMobileOpen(false)}
            >
              <span className="sidebar-link-icon" aria-hidden="true">{item.icon}</span>
              {showLabels && <span className="sidebar-link-label">{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user" title={displayName}>
            <Avatar name={displayName} email={displayEmail} size={34} />
            {showLabels && (
              <div className="sidebar-user-text">
                <span className="sidebar-user-name">{displayName}</span>
                <span className="sidebar-user-role">{displayRole}</span>
              </div>
            )}
          </div>
          <button
            className="sidebar-logout"
            onClick={handleLogout}
            aria-label="Logout"
            title={showLabels ? undefined : 'Logout'}
          >
            <span className="sidebar-link-icon" aria-hidden="true">🚪</span>
            {showLabels && <span className="sidebar-link-label">Logout</span>}
          </button>
        </div>
      </aside>

      {mobileOpen && <div className="sidebar-scrim" onClick={() => setMobileOpen(false)} aria-hidden="true" />}

      <div className="layout-body">
        <header className="layout-topbar" aria-label="Top navigation">
          <button
            type="button"
            className="topbar-menu-toggle"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Toggle navigation menu"
          >
            ☰
          </button>
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
            <Avatar name={displayName} email={displayEmail} size={36} />
          </div>
        </header>

        <main className="layout-content">
          <div className="route-fade" key={location.pathname}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
