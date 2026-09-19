/**
 * pages/CustomerSupport/components/TicketManagementView.js
 *
 * Enterprise Support Ticket Tracking & Management Center.
 * Features:
 *   - Search & multi-filter by Status, Priority, Category
 *   - Live dynamic SLA status (ON TRACK, AT RISK, BREACHED) and remaining time countdown
 *   - Status badges (OPEN, IN PROGRESS, WAITING FOR CUSTOMER, RESOLVED, CLOSED, ESCALATED)
 *   - Priority badges (LOW, MEDIUM, HIGH, CRITICAL)
 *   - Table View & Card Grid View
 *   - Quick "Create Ticket" trigger
 *   - Direct Ticket Detail inspector trigger
 */

import React, { useState, useEffect } from 'react';

export default function TicketManagementView({
  tickets,
  isLoading,
  categories,
  initialStatusFilter = 'ALL',
  onSelectTicket,
  onOpenCreateTicket,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter);
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'cards'

  // Synchronize when initialStatusFilter changes (e.g. from analytics drill-down click)
  useEffect(() => {
    if (initialStatusFilter) {
      setStatusFilter(initialStatusFilter);
    }
  }, [initialStatusFilter]);

  const filteredTickets = tickets.filter((t) => {
    if (statusFilter !== 'ALL' && (t.status || '').toLowerCase() !== statusFilter.toLowerCase()) {
      return false;
    }
    if (priorityFilter !== 'ALL' && (t.priority || '').toLowerCase() !== priorityFilter.toLowerCase()) {
      return false;
    }
    if (categoryFilter !== 'ALL' && t.category_id !== Number(categoryFilter)) {
      return false;
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const subjectMatch = t.subject && t.subject.toLowerCase().includes(q);
      const idMatch = String(t.id).includes(q);
      const custMatch = t.customer_name && t.customer_name.toLowerCase().includes(q);
      const descMatch = t.description && t.description.toLowerCase().includes(q);
      if (!subjectMatch && !idMatch && !custMatch && !descMatch) return false;
    }
    return true;
  });

  function getStatusBadge(status) {
    const s = (status || 'open').toLowerCase();
    const map = {
      open: { label: 'OPEN', class: 'cs-tkt-status-open' },
      assigned: { label: 'ASSIGNED', class: 'cs-tkt-status-assigned' },
      in_progress: { label: 'IN PROGRESS', class: 'cs-tkt-status-progress' },
      waiting_for_customer: { label: 'WAITING', class: 'cs-tkt-status-waiting' },
      resolved: { label: 'RESOLVED', class: 'cs-tkt-status-resolved' },
      closed: { label: 'CLOSED', class: 'cs-tkt-status-closed' },
      escalated: { label: 'ESCALATED', class: 'cs-tkt-status-escalated' },
    };
    const info = map[s] || { label: s.toUpperCase(), class: 'cs-tkt-status-open' };
    return <span className={`cs-tkt-status-badge ${info.class}`}>{info.label}</span>;
  }

  function getPriorityBadge(priority) {
    const p = (priority || 'medium').toLowerCase();
    const map = {
      low: { label: 'LOW', class: 'cs-prio-low' },
      medium: { label: 'MEDIUM', class: 'cs-prio-med' },
      high: { label: 'HIGH', class: 'cs-prio-high' },
      critical: { label: 'CRITICAL', class: 'cs-prio-crit' },
    };
    const info = map[p] || { label: p.toUpperCase(), class: 'cs-prio-med' };
    return <span className={`cs-prio-badge ${info.class}`}>{info.label}</span>;
  }

  function getSlaPill(t) {
    const slaStatus = (t.sla_status || 'on_track').toLowerCase();
    const isResolved = ['resolved', 'closed'].includes((t.status || '').toLowerCase());
    if (isResolved) {
      return (
        <div className="cs-sla-tag on_track" title="SLA target fulfilled">
          <span className="cs-sla-icon">✓</span> Met
        </div>
      );
    }
    const label = t.sla_time_remaining || (slaStatus === 'breached' ? 'Overdue' : 'On Track');
    return (
      <div className={`cs-sla-tag ${slaStatus}`} title={`SLA status: ${slaStatus.toUpperCase()}`}>
        <span className="cs-sla-dot"></span>
        <span>{label}</span>
      </div>
    );
  }

  return (
    <div className="cs-tickets-view">
      {/* Action Bar & Controls */}
      <div className="cs-tickets-toolbar">
        <div className="cs-toolbar-left">
          <div className="cs-search-box">
            <span className="cs-search-icon">🔍</span>
            <input
              type="text"
              placeholder="Search by ticket ID, subject, customer, keywords..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="cs-filter-group">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="cs-select"
            >
              <option value="ALL">All Statuses</option>
              <option value="OPEN">Open Queue</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="ESCALATED">Escalated</option>
              <option value="WAITING_FOR_CUSTOMER">Waiting for Customer</option>
              <option value="RESOLVED">Resolved</option>
              <option value="CLOSED">Closed</option>
            </select>

            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="cs-select"
            >
              <option value="ALL">All Priorities</option>
              <option value="CRITICAL">Critical Priority</option>
              <option value="HIGH">High Priority</option>
              <option value="MEDIUM">Medium Priority</option>
              <option value="LOW">Low Priority</option>
            </select>

            {categories && categories.length > 0 && (
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="cs-select"
              >
                <option value="ALL">All Categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <div className="cs-toolbar-right">
          <div className="cs-view-toggle">
            <button
              type="button"
              className={`cs-toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
              onClick={() => setViewMode('table')}
              title="Table View"
            >
              ☰ Table
            </button>
            <button
              type="button"
              className={`cs-toggle-btn ${viewMode === 'cards' ? 'active' : ''}`}
              onClick={() => setViewMode('cards')}
              title="Card Grid View"
            >
              ⊞ Cards
            </button>
          </div>

          <button
            type="button"
            className="cs-btn primary"
            onClick={() => onOpenCreateTicket()}
          >
            ➕ Create Ticket
          </button>
        </div>
      </div>

      {/* Tickets Content */}
      {isLoading ? (
        <div className="cs-loading-card">
          <div className="cs-spinner"></div>
          <p>Loading enterprise support tickets...</p>
        </div>
      ) : filteredTickets.length === 0 ? (
        <div className="cs-tickets-empty">
          <div className="cs-empty-icon">🎫</div>
          <h3>No support tickets found</h3>
          <p>No tickets match your filter criteria. You can create a new ticket anytime.</p>
          <button
            type="button"
            className="cs-btn primary"
            onClick={() => onOpenCreateTicket()}
          >
            Create New Support Ticket
          </button>
        </div>
      ) : viewMode === 'table' ? (
        /* Table View */
        <div className="cs-table-container">
          <table className="cs-tickets-table">
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Subject</th>
                <th>Category</th>
                <th>Priority</th>
                <th>Status</th>
                <th>SLA Countdown</th>
                <th>Assigned Team</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredTickets.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => onSelectTicket(t.id)}
                  className="cs-table-row-clickable"
                >
                  <td className="cs-tkt-id-cell">
                    <span className="cs-tkt-id-tag">#TKT-{t.id}</span>
                  </td>
                  <td className="cs-tkt-subject-cell">
                    <div className="cs-tkt-subject">{t.subject}</div>
                    <div className="cs-tkt-customer-sub">
                      {t.customer_name || 'Enterprise Customer'} • {t.customer_email || 'Verified Account'}
                    </div>
                  </td>
                  <td>
                    <span className="cs-tkt-category">{t.category_name || 'General Inquiry'}</span>
                  </td>
                  <td>{getPriorityBadge(t.priority)}</td>
                  <td>{getStatusBadge(t.status)}</td>
                  <td className="cs-sla-cell">{getSlaPill(t)}</td>
                  <td>
                    <span className="cs-tkt-team">{t.team_name || 'Support Pool'}</span>
                  </td>
                  <td className="cs-tkt-date-cell">
                    {t.created_at
                      ? new Date(t.created_at).toLocaleDateString([], {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : 'Recently'}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="cs-view-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectTicket(t.id);
                      }}
                    >
                      Inspect →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        /* Card Grid View */
        <div className="cs-ticket-cards-grid">
          {filteredTickets.map((t) => (
            <div
              key={t.id}
              className="cs-ticket-card"
              onClick={() => onSelectTicket(t.id)}
            >
              <div className="cs-tkt-card-header">
                <span className="cs-tkt-id-tag">#TKT-{t.id}</span>
                <div className="cs-tkt-card-badges">
                  {getPriorityBadge(t.priority)}
                  {getStatusBadge(t.status)}
                </div>
              </div>

              <h4 className="cs-tkt-card-title">{t.subject}</h4>

              <div className="cs-tkt-card-meta">
                <div className="cs-tkt-meta-item">
                  <span className="cs-meta-label">Category:</span>
                  <span className="cs-meta-val">{t.category_name || 'General'}</span>
                </div>
                <div className="cs-tkt-meta-item">
                  <span className="cs-meta-label">SLA Status:</span>
                  <span className="cs-meta-val">{getSlaPill(t)}</span>
                </div>
                <div className="cs-tkt-meta-item">
                  <span className="cs-meta-label">Team:</span>
                  <span className="cs-meta-val">{t.team_name || 'Support Team'}</span>
                </div>
                <div className="cs-tkt-meta-item">
                  <span className="cs-meta-label">Customer:</span>
                  <span className="cs-meta-val">{t.customer_name || 'Customer'}</span>
                </div>
              </div>

              <div className="cs-tkt-card-footer">
                <span className="cs-tkt-card-date">
                  {t.created_at
                    ? new Date(t.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                    : 'Recently'}
                </span>
                <span className="cs-card-inspect-link">Inspect Thread ➔</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
