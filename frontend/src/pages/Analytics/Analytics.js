/**
 * pages/Analytics/Analytics.js
 *
 * Static presentation page for the Analytics Dashboard module.
 * Uses a pure-CSS bar chart — no Recharts or extra libraries.
 * All data is hard-coded for demo purposes.
 */

import React from 'react';
import '../Recruitment/Recruitment.css';
import './Analytics.css';

/* Top KPI cards */
const KPIS = [
  { label: 'Total Tickets Resolved', value: '1,284', trend: '↑ 8.4%',  dir: 'up',   color: '#2563eb' },
  { label: 'Incidents This Month',   value: '37',    trend: '↓ 12%',   dir: 'down',  color: '#dc2626' },
  { label: 'Candidates Screened',    value: '319',   trend: '↑ 21%',   dir: 'up',   color: '#7c3aed' },
  { label: 'Meetings Summarised',    value: '68',    trend: '↑ 5%',    dir: 'up',   color: '#0891b2' },
  { label: 'AI Requests (30 days)',  value: '4,901', trend: '↑ 33%',   dir: 'up',   color: '#d97706' },
  { label: 'Active Employees',       value: '214',   trend: '↑ 2',     dir: 'up',   color: '#16a34a' },
];

/* Bar chart — weekly ticket volume */
const BARS = [
  { label: 'Mon', value: 38,  pct: 62 },
  { label: 'Tue', value: 52,  pct: 85 },
  { label: 'Wed', value: 61,  pct: 100 },
  { label: 'Thu', value: 44,  pct: 72 },
  { label: 'Fri', value: 49,  pct: 80 },
  { label: 'Sat', value: 18,  pct: 30 },
  { label: 'Sun', value: 11,  pct: 18 },
];

/* Module breakdown */
const MODULE_STATS = [
  { module: 'Customer Support',    requests: 1820, resolved: '94%', badge: 'green'  },
  { module: 'Incident Management', requests: 430,  resolved: '87%', badge: 'amber'  },
  { module: 'Recruitment AI',      requests: 960,  resolved: '100%',badge: 'green'  },
  { module: 'Meeting Intelligence',requests: 680,  resolved: '98%', badge: 'green'  },
  { module: 'Employee Management', requests: 310,  resolved: '100%',badge: 'green'  },
  { module: 'Analytics Engine',    requests: 701,  resolved: '100%',badge: 'green'  },
];

/* Top performing agents */
const AGENTS = [
  { name: 'Sarah Johnson',  role: 'Support Agent',   resolved: 148, satisfaction: '98%' },
  { name: 'Carlos Rivera',  role: 'IT Engineer',      resolved: 97,  satisfaction: '95%' },
  { name: 'Aisha Patel',    role: 'Support Agent',   resolved: 91,  satisfaction: '97%' },
  { name: 'Michael Chen',   role: 'DevOps Engineer',  resolved: 83,  satisfaction: '92%' },
];

export default function Analytics() {
  return (
    <div className="module-page">

      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon amber" aria-hidden="true">📊</div>
        <div>
          <h1>Analytics Dashboard</h1>
          <p>
            Cross-module KPIs, trends, and performance metrics — a single
            view of the entire enterprise AI platform.
          </p>
        </div>
      </div>

      {/* KPI cards */}
      <div className="analytics-grid">
        {KPIS.map((k) => (
          <div
            key={k.label}
            className="kpi-card"
            style={{ '--kpi-color': k.color }}
          >
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value">{k.value}</div>
            <div className={`kpi-trend ${k.dir}`}>{k.trend} vs last month</div>
          </div>
        ))}
      </div>

      {/* CSS bar chart — weekly ticket volume */}
      <div className="bar-chart-wrap">
        <h2>Weekly Ticket Volume (this week)</h2>
        <div className="bar-chart" role="img" aria-label="Bar chart of weekly ticket volume">
          {BARS.map((b) => (
            <div key={b.label} className="bar-group">
              <div className="bar-val">{b.value}</div>
              <div
                className="bar"
                style={{
                  height: `${b.pct}%`,
                  background: 'linear-gradient(180deg, #2563eb 0%, #7c3aed 100%)',
                }}
                title={`${b.label}: ${b.value} tickets`}
              />
              <div className="bar-label">{b.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Two-column bottom section */}
      <div className="two-col">

        {/* Module breakdown */}
        <div className="content-panel">
          <h2>AI Requests by Module</h2>
          <table className="data-table" aria-label="Module AI request stats">
            <thead>
              <tr>
                <th>Module</th>
                <th>Requests</th>
                <th>Success Rate</th>
              </tr>
            </thead>
            <tbody>
              {MODULE_STATS.map((m) => (
                <tr key={m.module}>
                  <td>{m.module}</td>
                  <td><strong>{m.requests.toLocaleString()}</strong></td>
                  <td>
                    <span className={`badge ${m.badge}`}>{m.resolved}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Top agents */}
        <div className="content-panel">
          <h2>Top Performing Agents</h2>
          <table className="data-table" aria-label="Top agent performance">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Role</th>
                <th>Resolved</th>
                <th>CSAT</th>
              </tr>
            </thead>
            <tbody>
              {AGENTS.map((a) => (
                <tr key={a.name}>
                  <td><strong>{a.name}</strong></td>
                  <td>{a.role}</td>
                  <td>{a.resolved}</td>
                  <td>
                    <span className="badge green">{a.satisfaction}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </div>
    </div>
  );
}
