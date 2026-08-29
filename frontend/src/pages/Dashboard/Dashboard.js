/**
 * pages/Dashboard/Dashboard.js
 *
 * Presentation-only dashboard.
 * Displays 6 enterprise module cards — all static, no API calls.
 * Clicking "Back to Login" returns to the login page.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import './Dashboard.css';

/**
 * Module card definitions.
 * Each entry maps to one card in the 3-column grid.
 *
 * Fields:
 *   id          — unique key
 *   icon        — emoji used as the visual icon
 *   title       — module display name
 *   description — one-line module summary shown on the card
 *   colorClass  — CSS class that sets the accent colour via custom properties
 *   status      — badge label shown in the card footer
 */
const MODULES = [
  {
    id: 'recruitment',
    icon: '🤖',
    title: 'AI Recruitment',
    description:
      'Automate resume screening, rank candidates by fit score, and schedule interviews with AI-driven insights.',
    colorClass: 'card-recruitment',
    status: 'Active',
  },
  {
    id: 'support',
    icon: '🎧',
    title: 'Customer Support',
    description:
      'AI-powered ticket management with automatic replies, priority triage, and real-time escalation detection.',
    colorClass: 'card-support',
    status: 'Active',
  },
  {
    id: 'incident',
    icon: '🚨',
    title: 'Incident Management',
    description:
      'Log, triage, and resolve incidents faster. AI suggests severity levels and assigns the right team automatically.',
    colorClass: 'card-incident',
    status: 'Active',
  },
  {
    id: 'meeting',
    icon: '🎙️',
    title: 'Meeting Intelligence',
    description:
      'Upload audio recordings. Get Whisper transcriptions, Gemini summaries, and action-item extraction instantly.',
    colorClass: 'card-meeting',
    status: 'Active',
  },
  {
    id: 'analytics',
    icon: '📊',
    title: 'Analytics Dashboard',
    description:
      'Cross-module KPIs, trend charts, and real-time metrics visualised with Recharts for data-driven decisions.',
    colorClass: 'card-analytics',
    status: 'Active',
  },
  {
    id: 'employee',
    icon: '👥',
    title: 'Employee Management',
    description:
      'Manage employee profiles, departments, and roles. AI-generated performance insights keep HR proactive.',
    colorClass: 'card-employee',
    status: 'Active',
  },
];

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="dashboard-page">

      {/* ── Top navigation bar ──────────────────────────────────── */}
      <nav className="dashboard-navbar" aria-label="Main navigation">
        <div className="navbar-brand">
          <span className="navbar-logo" aria-hidden="true">⚡</span>
          <span className="navbar-title">
            Unified <span>AI</span> Enterprise
          </span>
        </div>

        <div className="navbar-right">
          <span className="navbar-badge">Admin</span>

          {/* Avatar — clicking returns to login (sign-out simulation) */}
          <div
            className="navbar-avatar"
            role="button"
            tabIndex={0}
            aria-label="Sign out"
            title="Sign out"
            onClick={() => navigate('/login')}
            onKeyDown={(e) => e.key === 'Enter' && navigate('/login')}
          >
            A
          </div>
        </div>
      </nav>

      {/* ── Main content ────────────────────────────────────────── */}
      <main className="dashboard-main">
        <header className="dashboard-header">
          <h1>Enterprise Modules</h1>
          <p>
            Select a module to get started. All modules share the centralised
            AI Decision Engine.
          </p>
        </header>

        {/* ── 6-card grid ─────────────────────────────────────── */}
        <div
          className="modules-grid"
          role="list"
          aria-label="Enterprise module cards"
        >
          {MODULES.map((mod) => (
            <article
              key={mod.id}
              className={`module-card ${mod.colorClass}`}
              role="listitem"
              tabIndex={0}
              aria-label={`${mod.title} module`}
              /* Keyboard accessibility — Enter activates the card */
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.click()}
            >
              {/* Icon */}
              <div className="card-icon-wrap" aria-hidden="true">
                {mod.icon}
              </div>

              {/* Text */}
              <div className="card-body">
                <h2 className="card-title">{mod.title}</h2>
                <p className="card-description">{mod.description}</p>
              </div>

              {/* Footer */}
              <div className="card-footer">
                <span className="card-status active">{mod.status}</span>
                <span className="card-arrow" aria-hidden="true">→</span>
              </div>
            </article>
          ))}
        </div>
      </main>
    </div>
  );
}
