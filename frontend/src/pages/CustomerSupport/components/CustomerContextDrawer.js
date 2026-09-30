/**
 * pages/CustomerSupport/components/CustomerContextDrawer.js
 *
 * Slide-Over CRM Customer Profile Drawer:
 *   - Account details, organization tier, account health score
 *   - Dedicated SLA tier, priority level, assigned response team
 *   - Recent customer activity log
 *   - Action triggers (Create Ticket, Request Agent, View Tickets)
 */

import React from 'react';

export default function CustomerContextDrawer({
  isOpen,
  onClose,
  activeSession,
  ticketsCount = 0,
  onOpenCreateTicket,
  onOpenHandoff,
  onViewTickets,
}) {
  if (!isOpen) return null;

  return (
    <div className="cs-drawer-overlay" onClick={onClose}>
      <div className="cs-drawer-container" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="cs-drawer-header">
          <div className="cs-drawer-title-box">
            <span className="cs-drawer-icon">👤</span>
            <div>
              <h3>Customer Context</h3>
              <span className="cs-drawer-sub">Enterprise Profile & Account Health</span>
            </div>
          </div>
          <button type="button" className="cs-close-btn" onClick={onClose} title="Close Drawer">
            ✕
          </button>
        </div>

        {/* Drawer Body */}
        <div className="cs-drawer-body">
          {/* Customer Profile Card */}
          <div className="cs-drawer-section">
            <div className="cs-cust-profile-card">
              <div className="cs-cust-avatar-large">🏢</div>
              <div className="cs-cust-info-main">
                <div className="cs-cust-name-large">
                  {activeSession?.customer_name || 'Global Enterprise Corp'}
                </div>
                <div className="cs-cust-email-large">
                  {activeSession?.customer_email || 'admin@enterprise.ai'}
                </div>
                <div className="cs-cust-badge-row">
                  <span className="cs-status-badge active">● Active Account</span>
                  <span className="cs-tier-badge">Enterprise Tier</span>
                </div>
              </div>
            </div>
          </div>

          {/* Account Metrics & Health */}
          <div className="cs-drawer-section">
            <h4 className="cs-drawer-section-title">Account Diagnostics & SLA</h4>
            <div className="cs-drawer-grid">
              <div className="cs-drawer-stat-item">
                <span className="cs-stat-item-label">Account Health</span>
                <div className="cs-health-bar-container">
                  <div className="cs-health-bar-fill" style={{ width: '92%' }}></div>
                </div>
                <span className="cs-health-val green">92% Optimal</span>
              </div>

              <div className="cs-drawer-stat-item">
                <span className="cs-stat-item-label">Support SLA</span>
                <span className="cs-stat-item-value purple">24/7 Dedicated Priority</span>
              </div>

              <div className="cs-drawer-stat-item">
                <span className="cs-stat-item-label">Escalation Priority</span>
                <span className="cs-stat-item-value orange">High Priority</span>
              </div>

              <div className="cs-drawer-stat-item">
                <span className="cs-stat-item-label">Assigned Response Team</span>
                <span className="cs-stat-item-value">Enterprise Response Pool</span>
              </div>

              <div className="cs-drawer-stat-item">
                <span className="cs-stat-item-label">Active Support Tickets</span>
                <span className="cs-stat-item-value blue">{ticketsCount} Managed Tickets</span>
              </div>
            </div>
          </div>

          {/* Recent Activity Timeline */}
          <div className="cs-drawer-section">
            <h4 className="cs-drawer-section-title">Recent Activity Log</h4>
            <div className="cs-activity-timeline">
              <div className="cs-activity-item">
                <div className="cs-activity-dot blue"></div>
                <div className="cs-activity-content">
                  <div className="cs-activity-title">Live Chat Session Active</div>
                  <div className="cs-activity-time">In Progress • Enterprise AI Assistant</div>
                </div>
              </div>
              <div className="cs-activity-item">
                <div className="cs-activity-dot green"></div>
                <div className="cs-activity-content">
                  <div className="cs-activity-title">Password Security Verified</div>
                  <div className="cs-activity-time">2 hours ago • MFA Authenticated</div>
                </div>
              </div>
              <div className="cs-activity-item">
                <div className="cs-activity-dot purple"></div>
                <div className="cs-activity-content">
                  <div className="cs-activity-title">Billing Reconciliation Completed</div>
                  <div className="cs-activity-time">1 day ago • License Active</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Drawer Footer Actions */}
        <div className="cs-drawer-footer">
          <button
            type="button"
            className="cs-btn primary"
            onClick={() => {
              onClose();
              if (onOpenCreateTicket) onOpenCreateTicket();
            }}
          >
            🎫 Create Support Ticket
          </button>
          <button
            type="button"
            className="cs-btn secondary"
            onClick={() => {
              onClose();
              if (onOpenHandoff) onOpenHandoff();
            }}
          >
            👤 Request Human Specialist
          </button>
          <button
            type="button"
            className="cs-btn secondary"
            onClick={() => {
              onClose();
              if (onViewTickets) onViewTickets();
            }}
          >
            📂 View All Tickets
          </button>
        </div>
      </div>
    </div>
  );
}
