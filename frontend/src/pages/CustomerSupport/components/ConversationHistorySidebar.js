/**
 * pages/CustomerSupport/components/ConversationHistorySidebar.js
 *
 * Enterprise Conversation History Navigation Sidebar:
 *   - Prominent "New Conversation" action
 *   - Search previous chats
 *   - Grouped conversations (Today, Yesterday, Previous 7 Days, Older)
 *   - Message preview snippet, timestamp, and status badges (ACTIVE, ESCALATED, RESOLVED)
 *   - Delete session trigger with hover actions
 */

import React, { useState } from 'react';

export default function ConversationHistorySidebar({
  sessions = [],
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredSessions = sessions.filter((s) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    const titleMatch = s.title && s.title.toLowerCase().includes(term);
    const nameMatch = s.customer_name && s.customer_name.toLowerCase().includes(term);
    const idMatch = s.id && s.id.toLowerCase().includes(term);
    return titleMatch || nameMatch || idMatch;
  });

  const now = new Date();
  const todaySessions = [];
  const yesterdaySessions = [];
  const prevWeekSessions = [];
  const olderSessions = [];

  const oneDayMs = 24 * 60 * 60 * 1000;

  filteredSessions.forEach((s) => {
    const sDate = s.updated_at ? new Date(s.updated_at) : (s.created_at ? new Date(s.created_at) : now);
    const diffDays = Math.floor((now.setHours(0, 0, 0, 0) - new Date(sDate).setHours(0, 0, 0, 0)) / oneDayMs);

    if (diffDays <= 0) {
      todaySessions.push(s);
    } else if (diffDays === 1) {
      yesterdaySessions.push(s);
    } else if (diffDays <= 7) {
      prevWeekSessions.push(s);
    } else {
      olderSessions.push(s);
    }
  });

  function getStatusBadge(status) {
    switch ((status || 'active').toLowerCase()) {
      case 'resolved':
        return <span className="cs-hist-badge resolved">Resolved</span>;
      case 'escalated':
        return <span className="cs-hist-badge escalated">Escalated</span>;
      default:
        return <span className="cs-hist-badge active">Active</span>;
    }
  }

  function renderGroup(title, items) {
    if (!items || items.length === 0) return null;
    return (
      <div className="cs-history-group">
        <div className="cs-group-label">{title}</div>
        {items.map((s) => {
          const isSelected = s.id === activeSessionId;
          const displayTitle = s.title || (s.customer_name ? `${s.customer_name}'s Chat` : `Support Session #${s.id.slice(-6)}`);
          return (
            <div
              key={s.id}
              className={`cs-history-item ${isSelected ? 'selected' : ''}`}
              onClick={() => onSelectSession(s.id)}
            >
              <div className="cs-hist-top">
                <span className="cs-hist-icon">💬</span>
                <span className="cs-hist-title" title={displayTitle}>
                  {displayTitle}
                </span>
                {getStatusBadge(s.status)}
              </div>

              <div className="cs-hist-bottom">
                <span className="cs-hist-time">
                  {s.created_at
                    ? new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : 'Recent'}
                </span>
                <span className="cs-hist-count">
                  {s.message_count || 0} messages
                </span>
                <button
                  type="button"
                  className="cs-hist-del-btn"
                  title="Delete conversation"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm('Delete this conversation history?')) {
                      onDeleteSession(s.id);
                    }
                  }}
                >
                  🗑️
                </button>
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="cs-history-sidebar">
      {/* Sidebar Header with New Chat Button */}
      <div className="cs-history-header">
        <button
          type="button"
          className="cs-new-chat-btn"
          onClick={onNewSession}
          title="Start a new chat conversation"
        >
          <span className="cs-btn-icon">➕</span> New Conversation
        </button>

        <div className="cs-history-search">
          <span className="cs-hist-search-icon">🔍</span>
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Grouped Conversations List */}
      <div className="cs-history-list">
        {filteredSessions.length === 0 ? (
          <div className="cs-history-empty">
            <span className="cs-empty-chat-icon">💬</span>
            <p>No conversations found.</p>
          </div>
        ) : (
          <>
            {renderGroup("Today", todaySessions)}
            {renderGroup("Yesterday", yesterdaySessions)}
            {renderGroup("Previous 7 Days", prevWeekSessions)}
            {renderGroup("Older Conversations", olderSessions)}
          </>
        )}
      </div>
    </div>
  );
}
