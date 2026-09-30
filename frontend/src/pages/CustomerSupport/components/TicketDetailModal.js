/**
 * pages/CustomerSupport/components/TicketDetailModal.js
 *
 * Detailed Ticket Inspector Modal:
 *   - Ticket metadata (Category, Team, Customer, Channel, SLA)
 *   - AI Escalation Synopsis
 *   - Linked Chat Conversation Transcript
 *   - Follow-up message thread / timeline
 *   - Status & Priority updates
 *   - Direct message reply composer
 */

import React, { useState } from 'react';

export default function TicketDetailModal({
  ticket,
  onClose,
  onUpdateStatus,
  onAddMessage,
}) {
  const [replyText, setReplyText] = useState('');
  const [isSubmittingReply, setIsSubmittingReply] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState(ticket?.status || 'open');

  if (!ticket) return null;

  async function handleSendReply(e) {
    e.preventDefault();
    const text = replyText.trim();
    if (!text || isSubmittingReply) return;
    setIsSubmittingReply(true);
    try {
      await onAddMessage(ticket.id, text);
      setReplyText('');
    } finally {
      setIsSubmittingReply(false);
    }
  }

  function handleStatusChange(e) {
    const newStatus = e.target.value;
    setSelectedStatus(newStatus);
    onUpdateStatus(ticket.id, { status: newStatus });
  }

  function getPriorityColor(p) {
    switch ((p || '').toLowerCase()) {
      case 'critical':
        return '#dc2626';
      case 'high':
        return '#ea580c';
      case 'medium':
        return '#d97706';
      default:
        return '#16a34a';
    }
  }

  return (
    <div className="cs-modal-overlay" onClick={onClose}>
      <div className="cs-ticket-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="cs-modal-header">
          <div className="cs-modal-title-box">
            <span className="cs-tkt-id-tag">#TKT-{ticket.id}</span>
            <h2>{ticket.subject}</h2>
          </div>
          <button type="button" className="cs-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="cs-modal-body">
          {/* Top Metadata Bar */}
          <div className="cs-tkt-meta-strip">
            <div className="cs-meta-cell">
              <span className="cs-cell-label">Status</span>
              <select
                value={selectedStatus}
                onChange={handleStatusChange}
                className="cs-status-select"
              >
                <option value="open">OPEN</option>
                <option value="in_progress">IN PROGRESS</option>
                <option value="waiting_for_customer">WAITING FOR CUSTOMER</option>
                <option value="escalated">ESCALATED</option>
                <option value="resolved">RESOLVED</option>
                <option value="closed">CLOSED</option>
              </select>
            </div>

            <div className="cs-meta-cell">
              <span className="cs-cell-label">Priority</span>
              <span
                className="cs-cell-val"
                style={{ color: getPriorityColor(ticket.priority), fontWeight: 700 }}
              >
                {(ticket.priority || 'MEDIUM').toUpperCase()}
              </span>
            </div>

            <div className="cs-meta-cell">
              <span className="cs-cell-label">SLA Target</span>
              <span className={`cs-sla-tag ${ticket.sla_status || 'on_track'}`}>
                {ticket.sla_time_remaining || 'Within Target'}
              </span>
            </div>

            <div className="cs-meta-cell">
              <span className="cs-cell-label">Assigned Team</span>
              <span className="cs-cell-val">
                {ticket.team?.name || 'Support Pool'}
              </span>
            </div>

            <div className="cs-meta-cell">
              <span className="cs-cell-label">Category</span>
              <span className="cs-cell-val">
                {ticket.category?.name || 'General Inquiry'}
              </span>
            </div>

            <div className="cs-meta-cell">
              <span className="cs-cell-label">Customer</span>
              <span className="cs-cell-val">
                {ticket.customer_name || 'Enterprise Customer'}
              </span>
            </div>
          </div>

          {/* AI Escalation / Issue Summary Box */}
          {ticket.ai_summary && (
            <div className="cs-ai-summary-card">
              <div className="cs-ai-summary-title">
                <span>🤖 AI Triage & Escalation Summary</span>
              </div>
              <p className="cs-ai-summary-text">{ticket.ai_summary}</p>
              {ticket.escalation_reason && (
                <div className="cs-ai-reason-badge">
                  <strong>Trigger:</strong> {ticket.escalation_reason}
                </div>
              )}
            </div>
          )}

          {/* Detailed Problem Description */}
          <div className="cs-tkt-section">
            <h4 className="cs-tkt-section-title">Description</h4>
            <div className="cs-tkt-desc-box">
              {ticket.description.split('\n').map((line, i) => (
                <p key={i} style={{ margin: line ? '0.2rem 0' : '0.4rem 0' }}>
                  {line}
                </p>
              ))}
            </div>
          </div>

          {/* Linked Chat Transcript (if escalated from chatbot) */}
          {ticket.chat_transcript && ticket.chat_transcript.length > 0 && (
            <div className="cs-tkt-section">
              <h4 className="cs-tkt-section-title">
                Linked Chat Session Transcript (#{ticket.session_id})
              </h4>
              <div className="cs-transcript-box">
                {ticket.chat_transcript.map((m, idx) => (
                  <div key={idx} className={`cs-transcript-row ${m.sender_type}`}>
                    <span className="cs-trans-sender">
                      {m.sender_type === 'customer' ? 'Customer' : 'AI Bot'}:
                    </span>
                    <span className="cs-trans-msg">{m.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Ticket Messages Thread */}
          <div className="cs-tkt-section">
            <h4 className="cs-tkt-section-title">Message Thread ({ticket.messages?.length || 0})</h4>
            <div className="cs-thread-list">
              {ticket.messages && ticket.messages.length > 0 ? (
                ticket.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`cs-thread-item ${msg.is_ai ? 'ai' : msg.sender_id === 1 ? 'user' : 'agent'}`}
                  >
                    <div className="cs-thread-header">
                      <span className="cs-thread-author">
                        {msg.is_ai ? '🤖 ' : '👤 '}
                        {msg.sender_name || (msg.is_ai ? 'AI Assistant' : 'Support Agent')}
                      </span>
                      <span className="cs-thread-time">
                        {msg.created_at
                          ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                          : 'Recent'}
                      </span>
                    </div>
                    <div className="cs-thread-text">{msg.message}</div>
                  </div>
                ))
              ) : (
                <p className="cs-thread-empty">No updates posted yet on this ticket thread.</p>
              )}
            </div>
          </div>
        </div>

        {/* Modal Footer: Reply Composer */}
        <form className="cs-modal-footer-reply" onSubmit={handleSendReply}>
          <input
            type="text"
            className="cs-reply-input"
            placeholder="Post a reply or status update to this ticket..."
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            disabled={isSubmittingReply}
          />
          <button
            type="submit"
            className="cs-btn primary"
            disabled={!replyText.trim() || isSubmittingReply}
          >
            {isSubmittingReply ? 'Posting...' : 'Post Reply'}
          </button>
        </form>
      </div>
    </div>
  );
}
