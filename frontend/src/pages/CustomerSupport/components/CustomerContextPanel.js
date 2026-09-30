/**
 * pages/CustomerSupport/components/CustomerContextPanel.js
 *
 * Right-side Enterprise Context & Analytics Panel:
 *   - Customer profile & organization tier
 *   - Current ticket SLA status & support priority
 *   - Live operational support metrics
 *   - Verified Knowledge Base summary
 */

import React from 'react';

export default function CustomerContextPanel({
  stats,
  activeSession,
  ticketsCount,
  onOpenCreateTicket,
  onOpenHandoff,
  onDrillDown,
}) {
  return (
    <div className="cs-side-panel">
      {/* 1. Customer Context Card */}
      <div className="cs-panel-card">
        <div className="cs-card-header">
          <h3>👤 Customer Context</h3>
          <span className="cs-tier-tag">Enterprise Tier</span>
        </div>

        <div className="cs-cust-profile">
          <div className="cs-cust-avatar">🏢</div>
          <div>
            <div className="cs-cust-name">
              {activeSession?.customer_name || 'Global Enterprise Corp'}
            </div>
            <div className="cs-cust-email">
              {activeSession?.customer_email || 'admin@enterprise.ai'}
            </div>
          </div>
        </div>

        <div className="cs-cust-details">
          <div className="cs-cust-row">
            <span className="cs-cust-label">Account Status:</span>
            <span className="cs-cust-val green">● Active (Good Standing)</span>
          </div>
          <div className="cs-cust-row">
            <span className="cs-cust-label">Support SLA:</span>
            <span className="cs-cust-val purple">24/7 Dedicated Priority</span>
          </div>
          <div className="cs-cust-row">
            <span className="cs-cust-label">Support Priority:</span>
            <span className="cs-cust-val orange">High Priority Escalation</span>
          </div>
          <div className="cs-cust-row">
            <span className="cs-cust-label">Assigned Support Pool:</span>
            <span className="cs-cust-val">Enterprise Response Team</span>
          </div>
        </div>

        <div className="cs-cust-actions">
          <button
            type="button"
            className="cs-cust-btn primary"
            onClick={() => onOpenCreateTicket()}
          >
            🎫 New Ticket
          </button>
          <button
            type="button"
            className="cs-cust-btn secondary"
            onClick={onOpenHandoff}
          >
            👤 Request Agent
          </button>
        </div>
      </div>

      {/* 2. Live Operational Support Metrics */}
      <div className="cs-panel-card">
        <div className="cs-card-header">
          <h3>📊 Support Analytics</h3>
          <span className="cs-badge-demo">Demo Telemetry</span>
        </div>

        <div className="cs-stat-grid">
          <div
            className="cs-stat-box cs-clickable-stat"
            onClick={() => onDrillDown && onDrillDown('tickets', 'ALL')}
            title="Click to view all tickets"
          >
            <div className="cs-stat-box-label">Total Tickets</div>
            <div className="cs-stat-box-value">{stats.total_tickets || ticketsCount || 12}</div>
          </div>
          <div
            className="cs-stat-box cs-clickable-stat"
            onClick={() => onDrillDown && onDrillDown('tickets', 'OPEN')}
            title="Click to filter Open queue"
          >
            <div className="cs-stat-box-label">Open Tickets</div>
            <div className="cs-stat-box-value orange">{stats.open_tickets || 3}</div>
          </div>
          <div
            className="cs-stat-box cs-clickable-stat"
            onClick={() => onDrillDown && onDrillDown('tickets', 'ESCALATED')}
            title="Click to filter Escalated tickets"
          >
            <div className="cs-stat-box-label">Escalated</div>
            <div className="cs-stat-box-value red">{stats.escalated_tickets || 1}</div>
          </div>
          <div
            className="cs-stat-box cs-clickable-stat"
            onClick={() => onDrillDown && onDrillDown('tickets', 'RESOLVED')}
            title="Click to filter Resolved tickets"
          >
            <div className="cs-stat-box-label">Resolved</div>
            <div className="cs-stat-box-value green">{stats.resolved_tickets || 8}</div>
          </div>
          <div
            className="cs-stat-box cs-clickable-stat"
            onClick={() => onDrillDown && onDrillDown('kb', 'ALL')}
            title="Click to open Knowledge Base directory"
          >
            <div className="cs-stat-box-label">Verified Articles</div>
            <div className="cs-stat-box-value blue">{stats.total_knowledge_docs || 5}</div>
          </div>
          <div className="cs-stat-box">
            <div className="cs-stat-box-label">AI Resolution Rate</div>
            <div className="cs-stat-box-value green">92.4%</div>
          </div>
        </div>

        <div className="cs-engine-badge-box">
          <span className="cs-engine-dot"></span>
          <span>Engine: Grounded Gemini AI + BM25 RAG</span>
        </div>
      </div>

      {/* 3. System Health & Knowledge Topics */}
      <div className="cs-panel-card">
        <div className="cs-card-header">
          <h3>🛡️ SLA Response Guarantee</h3>
        </div>
        <ul className="cs-sla-list">
          <li className="cs-sla-item">
            <span className="cs-sla-prio crit">CRITICAL</span>
            <span className="cs-sla-time">&lt; 1 hour (24/7)</span>
          </li>
          <li className="cs-sla-item">
            <span className="cs-sla-prio high">HIGH</span>
            <span className="cs-sla-time">&lt; 4 hours</span>
          </li>
          <li className="cs-sla-item">
            <span className="cs-sla-prio med">MEDIUM</span>
            <span className="cs-sla-time">&lt; 24 hours</span>
          </li>
          <li className="cs-sla-item">
            <span className="cs-sla-prio low">LOW</span>
            <span className="cs-sla-time">&lt; 48 hours</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
