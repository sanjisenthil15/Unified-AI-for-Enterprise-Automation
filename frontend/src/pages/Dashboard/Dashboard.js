/**
 * pages/Dashboard/Dashboard.js
 *
 * Landing page: 6 enterprise module cards, each navigating to its module.
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
    to: '/hr',
  },
  {
    id: 'support',
    icon: '🎧',
    title: 'Customer Support',
    description:
      'AI-powered ticket management with automatic replies, priority triage, and real-time escalation detection.',
    colorClass: 'card-support',
    status: 'Active',
    to: '/customer-support',
  },
  {
    id: 'incident',
    icon: '🚨',
    title: 'Incident Management',
    description:
      'Log, triage, and resolve incidents faster. AI suggests severity levels and assigns the right team automatically.',
    colorClass: 'card-incident',
    status: 'Active',
    to: '/incidents',
  },
  {
    id: 'meeting',
    icon: '🎙️',
    title: 'Meeting Intelligence',
    description:
      'Upload audio recordings. Get Whisper transcriptions, Gemini summaries, and action-item extraction instantly.',
    colorClass: 'card-meeting',
    status: 'Active',
    to: '/meetings',
  },
  {
    id: 'analytics',
    icon: '📊',
    title: 'Analytics Dashboard',
    description:
      'Cross-module KPIs, trend charts, and real-time metrics visualised with Recharts for data-driven decisions.',
    colorClass: 'card-analytics',
    status: 'Active',
    to: '/analytics',
  },
  {
    id: 'employee',
    icon: '👥',
    title: 'Employee Management',
    description:
      'Manage employee profiles, departments, and roles. AI-generated performance insights keep HR proactive.',
    colorClass: 'card-employee',
    status: 'Active',
    to: '/employees',
  },
];

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="dashboard-page">

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
              onClick={() => navigate(mod.to)}
              /* Keyboard accessibility — Enter activates the card */
              onKeyDown={(e) => e.key === 'Enter' && navigate(mod.to)}
              style={{ cursor: 'pointer' }}
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
