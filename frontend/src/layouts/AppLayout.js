/**
 * layouts/AppLayout.js
 *
 * Shared layout shell — sidebar + topbar + <Outlet>.
 *
 * Role-based sidebar: each item's `roles` (null = everyone) decides
 * whether it's shown for the current user's role. This only hides the
 * link — real enforcement for role-sensitive pages lives in App.js's
 * ProtectedRoute(allowedRoles=...).
 * No CSS changes — reuses AppLayout.css exactly as-is.
 */

import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import './AppLayout.css';

const NAV_ITEMS = [
  { to: '/dashboard',        icon: '🏠', label: 'Dashboard',            roles: null },
  { to: '/hr',                icon: '🧑‍💼', label: 'HR Recruitment',     roles: null },
  { to: '/customer-support',  icon: '🎧', label: 'Customer Support',    roles: null },
  { to: '/incidents',         icon: '🚨', label: 'Incident Management', roles: null },
  { to: '/meetings',          icon: '🎙️', label: 'Meetings',            roles: null },
  { to: '/employees',         icon: '👥', label: 'Employee Management', roles: ['admin', 'hr_manager'] },
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
