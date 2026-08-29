/**
 * layouts/AppLayout.js
 *
 * Shared layout shell — sidebar + topbar + <Outlet>.
 *
 * Role-based sidebar: HR users only see the Recruitment link.
 * All other roles see the full navigation.
 * No CSS changes — reuses AppLayout.css exactly as-is.
 */

import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import './AppLayout.css';

const ALL_NAV = [
  { to: '/dashboard',        icon: '🏠', label: 'Dashboard' },
  { to: '/recruitment',      icon: '🤖', label: 'Recruitment' },
  { to: '/customer-support', icon: '🎧', label: 'Customer Support' },
  { to: '/incidents',        icon: '🚨', label: 'Incident Management' },
  { to: '/meetings',         icon: '🎙️', label: 'Meetings' },
  { to: '/analytics',        icon: '📊', label: 'Analytics' },
];

const HR_NAV = [
  { to: '/hr',          icon: '🏠', label: 'HR Dashboard' },
  { to: '/recruitment', icon: '🤖', label: 'Recruitment' },
];

export default function AppLayout() {
  const navigate = useNavigate();

  const [user] = useState(() => {
    try { return JSON.parse(localStorage.getItem('user')) || null; }
    catch { return null; }
  });

  const role         = user?.role?.name?.toLowerCase() ?? '';
  const displayName  = user?.full_name  ?? 'User';
  const displayRole  = user?.role?.name ?? '';
  const avatarLetter = displayName.charAt(0).toUpperCase();

  // HR only sees HR_NAV; everyone else sees ALL_NAV
  const navItems = role === 'hr' ? HR_NAV : ALL_NAV;

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
