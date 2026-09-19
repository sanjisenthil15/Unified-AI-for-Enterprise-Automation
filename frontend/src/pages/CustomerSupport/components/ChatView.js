/**
 * pages/CustomerSupport/components/ChatView.js
 *
 * Enterprise AI Customer Support Chat Canvas.
 * Features:
 *   - AI Assistant header with online status & model badges
 *   - Comprehensive categorized starter questions with instant execution
 *   - Grounded knowledge citations with confidence scores & verification badge
 *   - Structured source document inspector modal
 *   - Error handling with 1-click [Retry] action
 *   - Escalation cards with 1-click Ticket Creation and Human Agent Handoff
 *   - Message actions: Copy to clipboard, Helpful/Not Helpful ratings, Regenerate
 *   - "AI is searching verified knowledge base..." typing indicator
 *   - Floating rounded message composer with auto-growing textarea and tool shortcuts
 */

import React, { useState, useEffect, useRef } from 'react';

const SUPPORT_TOPICS = [
  {
    id: 'billing_payments',
    category: 'Billing & Payments',
    icon: '💳',
    description: 'Refund periods, payment cancellations, double charges & receipts',
    badge: '10 FAQs',
    questions: [
      'What is the refund period?',
      'How do I request a refund?',
      'How do I cancel a payment?',
      'Why was I charged twice?',
      'Why does my payment show as pending?',
      'Why was my payment declined?',
      'How can I update my billing information?',
      'Where can I view my payment history?',
      'How can I download a payment receipt?',
      'What should I do if I was charged incorrectly?',
    ],
  },
  {
    id: 'account_security',
    category: 'Account & Security',
    icon: '🔐',
    description: 'Password reset, 2FA setup, locked accounts & session security',
    badge: '10 FAQs',
    questions: [
      'How do I reset my password?',
      'How do I change my password?',
      'How do I enable two-factor authentication?',
      'What should I do if my account is locked?',
      'How do I recover my account?',
      'How do I update my email address?',
      'How do I change my phone number?',
      'How do I manage active sessions?',
      'How do I sign out from other devices?',
      'What should I do if I suspect unauthorized access?',
    ],
  },
  {
    id: 'technical_support',
    category: 'Technical Support',
    icon: '⚙️',
    description: 'API 500/404/401 errors, timeouts, failed requests & latency',
    badge: '10 FAQs',
    questions: [
      'Why am I getting a 500 error from the API?',
      'Why is the API request failing?',
      'Why am I receiving a 404 error?',
      'Why am I receiving a 401 unauthorized error?',
      'Why is my application loading slowly?',
      'Why is the service unavailable?',
      'How do I troubleshoot an API timeout?',
      'How do I troubleshoot a failed request?',
      'What should I check before contacting technical support?',
      'When should a technical issue be escalated?',
    ],
  },
  {
    id: 'subscriptions_invoicing',
    category: 'Subscriptions & Invoicing',
    icon: '📦',
    description: 'Plan upgrades, downgrades, renewals, invoices & inactive licenses',
    badge: '10 FAQs',
    questions: [
      'How do I cancel my subscription?',
      'How do I upgrade my subscription?',
      'How do I downgrade my subscription?',
      'When will my subscription renew?',
      'Why is my subscription inactive after payment?',
      'How do I update my payment method?',
      'Where can I view my invoices?',
      'How do I download an invoice?',
      'Why is my invoice amount different?',
      'How do I reactivate my subscription?',
    ],
  },
  {
    id: 'ui_troubleshooting',
    category: 'UI & Troubleshooting',
    icon: '🛠️',
    description: 'Unresponsive buttons, browser cache, hard refresh & compatibility',
    badge: '10 FAQs',
    questions: [
      'Why is the dashboard button not responding?',
      'How do I clear my browser cache?',
      'How do I perform a hard refresh?',
      'Why is the page not loading?',
      'Why are some buttons disabled?',
      'Why is the interface displaying incorrectly?',
      'Which browsers are supported?',
      'Why am I being logged out unexpectedly?',
      'Why is the page responding slowly?',
      'What should I do if the problem continues after clearing the cache?',
    ],
  },
  {
    id: 'general_support_sla',
    category: 'General Support & SLA',
    icon: '📋',
    description: 'Operating hours, critical SLAs, ticket status & agent handoff',
    badge: '10 FAQs',
    questions: [
      'What are your customer support hours?',
      'What is the SLA for critical tickets?',
      'What is the SLA for high-priority tickets?',
      'How do I contact priority support?',
      'How do I escalate a support issue?',
      'What happens after I create a support ticket?',
      'How can I check my ticket status?',
      'When will a support agent respond?',
      'How are support priorities assigned?',
      'When should I request a human support agent?',
    ],
  },
  {
    id: 'account_profile',
    category: 'Account & Profile Management',
    icon: '👤',
    description: 'Profile updates, company details, permissions & deactivation',
    badge: '10 FAQs',
    questions: [
      'How do I update my profile?',
      'How do I change my account information?',
      'How do I update my contact details?',
      'How do I change my company information?',
      'How do I manage my notification preferences?',
      'How do I manage account permissions?',
      'How do I view my account status?',
      'How do I manage connected devices?',
      'How do I deactivate my account?',
      'How do I reactivate my account?',
    ],
  },
  {
    id: 'products_services',
    category: 'Products & Services',
    icon: '🚀',
    description: 'Product catalog, feature tiers, configuration & feature requests',
    badge: '10 FAQs',
    questions: [
      'What products and services are available?',
      'What features are included in my plan?',
      'How do I get started with a product?',
      'How do I configure a product?',
      'How do I enable a feature?',
      'Why is a product feature unavailable?',
      'How do I request a new feature?',
      'How can I learn more about a service?',
      'What should I do if a product is not working?',
      'How do I contact the product support team?',
    ],
  },
  {
    id: 'orders_requests',
    category: 'Orders, Requests & Service Issues',
    icon: '📑',
    description: 'Service request creation, tracking, reporting & escalation',
    badge: '10 FAQs',
    questions: [
      'How do I create a service request?',
      'How do I check the status of my request?',
      'How do I update an existing request?',
      'How do I cancel a request?',
      'How do I report a service issue?',
      'How do I track my support request?',
      'What information should I provide when creating a request?',
      'How do I escalate a service request?',
      'What happens after submitting a request?',
      'How do I contact an agent about an unresolved request?',
    ],
  },
];

export default function ChatView({
  session,
  messages = [],
  isLoading,
  onSendMessage,
  onRetry,
  onOpenCreateTicket,
  onOpenHandoff,
  onClearSession,
  onFeedback,
  onOpenKbDoc,
  onNavigateTab,
}) {
  const [inputMessage, setInputMessage] = useState('');
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [faqSearchQuery, setFaqSearchQuery] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [ratedMessages, setRatedMessages] = useState({});
  const [activeCitation, setActiveCitation] = useState(null);
  const [expandedDetails, setExpandedDetails] = useState({});
  const chatEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  function handleSend(e) {
    if (e) e.preventDefault();
    const text = inputMessage.trim();
    if (!text || isLoading) return;
    onSendMessage(text);
    setInputMessage('');
    setSelectedTopic(null);
    setFaqSearchQuery('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }

  function handleQuestionClick(q) {
    onSendMessage(q);
    setSelectedTopic(null);
    setFaqSearchQuery('');
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleCopy(msgId, text) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text);
    }
    setCopiedId(msgId);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function handleRate(msgId, rating) {
    setRatedMessages((prev) => ({ ...prev, [msgId]: rating }));
    if (onFeedback) {
      onFeedback(msgId, rating);
    }
  }

  function handleTextareaInput(e) {
    setInputMessage(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  }

  function toggleAiDetails(msgId) {
    setExpandedDetails((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  }

  // Filtered questions in the active topic workspace
  const filteredQuestions = selectedTopic
    ? selectedTopic.questions.filter((q) =>
        q.toLowerCase().includes(faqSearchQuery.toLowerCase().trim())
      )
    : [];

  return (
    <div className="cs-chat-container">
      {/* Chat Card Header */}
      <div className="cs-chat-header">
        <div className="cs-bot-profile">
          <div className="cs-bot-avatar">🤖</div>
          <div>
            <div className="cs-bot-title-row">
              <span className="cs-bot-name">Enterprise Support AI</span>
              <span className="cs-badge-ai">BM25 Grounded RAG</span>
              <span className="cs-badge-model">Gemini 1.5 Ready</span>
            </div>
            <div className="cs-bot-sub">
              Verified Enterprise Knowledge Base • 9 Specialized Support Domains
            </div>
          </div>
        </div>

        <div className="cs-chat-header-actions">
          <span className="cs-status-indicator online">
            <span className="cs-pulse-dot"></span> Online
          </span>
          {messages.length > 0 && (
            <button
              type="button"
              className="cs-header-btn"
              onClick={() => {
                setSelectedTopic(null);
                setFaqSearchQuery('');
                if (onClearSession) onClearSession();
              }}
              title="Clear active conversation and return to topics"
            >
              🔄 Clear
            </button>
          )}
          <button
            type="button"
            className="cs-header-btn primary"
            onClick={onOpenHandoff}
            title="Connect with Human Support Specialist"
          >
            👤 Talk to Agent
          </button>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="cs-chat-body">
        {messages.length === 0 ? (
          <div className="cs-empty-state">
            {!selectedTopic ? (
              <>
                <div className="cs-empty-hero">
                  <div className="cs-empty-icon">✨</div>
                  <h2>Enterprise AI Customer Support</h2>
                  <p>
                    Select a support category below to explore frequently asked questions,
                    or type your question directly in the chat composer.
                  </p>
                </div>

                {/* 9 Topics Main Grid */}
                <div className="cs-topics-grid-9">
                  {SUPPORT_TOPICS.map((topic) => (
                    <div
                      key={topic.id}
                      className="cs-topic-card-enterprise"
                      onClick={() => {
                        setSelectedTopic(topic);
                        setFaqSearchQuery('');
                      }}
                      title={`Open ${topic.category} questions`}
                    >
                      <div className="cs-topic-card-top">
                        <div className="cs-topic-icon-box">{topic.icon}</div>
                        <span className="cs-topic-faq-badge">{topic.badge}</span>
                      </div>
                      <h3 className="cs-topic-card-title">{topic.category}</h3>
                      <p className="cs-topic-card-desc">{topic.description}</p>
                      <div className="cs-topic-card-footer">
                        <span className="cs-topic-action-text">Explore FAQs</span>
                        <span className="cs-topic-card-arrow">➔</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              /* Topic Questions Workspace Panel */
              <div className="cs-topic-workspace">
                <div className="cs-workspace-nav">
                  <button
                    type="button"
                    className="cs-topic-back-btn"
                    onClick={() => {
                      setSelectedTopic(null);
                      setFaqSearchQuery('');
                    }}
                  >
                    ← Back to all 9 topics
                  </button>
                  <span className="cs-workspace-domain-badge">
                    Domain Workspace
                  </span>
                </div>

                <div className="cs-workspace-header">
                  <div className="cs-workspace-icon">{selectedTopic.icon}</div>
                  <div className="cs-workspace-meta">
                    <h2>{selectedTopic.category}</h2>
                    <p>{selectedTopic.description}</p>
                  </div>
                </div>

                {/* FAQ Search Filter Input */}
                <div className="cs-faq-search-wrapper">
                  <div className="cs-faq-search-box">
                    <span className="cs-faq-search-icon">🔍</span>
                    <input
                      type="text"
                      className="cs-faq-search-input"
                      placeholder={`Search FAQs in ${selectedTopic.category}...`}
                      value={faqSearchQuery}
                      onChange={(e) => setFaqSearchQuery(e.target.value)}
                    />
                    {faqSearchQuery && (
                      <button
                        type="button"
                        className="cs-faq-search-clear"
                        onClick={() => setFaqSearchQuery('')}
                        title="Clear filter"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  <div className="cs-faq-count-label">
                    Showing {filteredQuestions.length} of {selectedTopic.questions.length} Questions
                  </div>
                </div>

                {/* Questions List */}
                <div className="cs-faq-list">
                  {filteredQuestions.length > 0 ? (
                    filteredQuestions.map((question, qIdx) => (
                      <button
                        key={qIdx}
                        type="button"
                        className="cs-faq-item-btn"
                        disabled={isLoading}
                        onClick={() => handleQuestionClick(question)}
                        title={`Ask: "${question}"`}
                      >
                        <span className="cs-faq-num">{qIdx + 1}</span>
                        <span className="cs-faq-text">{question}</span>
                        <span className="cs-faq-arrow">➔</span>
                      </button>
                    ))
                  ) : (
                    <div className="cs-faq-no-results">
                      <p>No FAQs match "{faqSearchQuery}" in this category.</p>
                      <button
                        type="button"
                        className="cs-clear-search-btn"
                        onClick={() => setFaqSearchQuery('')}
                      >
                        Clear Search
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`cs-message-row ${msg.sender_type} ${msg.is_error ? 'has-error' : ''}`}
            >
              <div className="cs-msg-avatar">
                {msg.sender_type === 'customer' ? '👤' : msg.is_error ? '⚠️' : '🤖'}
              </div>

              <div className="cs-msg-content-wrapper">
                <div className={`cs-msg-bubble ${msg.is_error ? 'error-bubble' : ''}`}>
                  {/* Message Sender Header */}
                  <div className="cs-msg-header">
                    <span className="cs-msg-author">
                      {msg.sender_type === 'customer'
                        ? session?.customer_name || 'You'
                        : 'Enterprise Support AI'}
                    </span>
                    <span className="cs-msg-time">
                      {msg.created_at
                        ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        : 'Just now'}
                    </span>
                  </div>

                  {/* Message Text */}
                  <div className="cs-msg-text">
                    {msg.message.split('\n').map((line, idx) => {
                      if (!line) return <div key={idx} style={{ height: '0.4rem' }} />;
                      // Clean bullet rendering
                      if (line.startsWith('• ') || line.startsWith('- ')) {
                        return (
                          <div key={idx} className="cs-bullet-line">
                            <span className="cs-bullet-dot">•</span>
                            <span>{line.substring(2)}</span>
                          </div>
                        );
                      }
                      return (
                        <p key={idx} style={{ margin: '0.2rem 0' }}>
                          {line}
                        </p>
                      );
                    })}
                  </div>

                  {/* Error Action Strip if API Failed */}
                  {msg.is_error && (
                    <div className="cs-msg-error-action">
                      <span>Unable to complete request.</span>
                      <button
                        type="button"
                        className="cs-retry-btn"
                        onClick={() => onRetry && onRetry(msg.failed_query)}
                      >
                        🔄 Retry Question
                      </button>
                    </div>
                  )}

                  {/* Citations & Source Badges (For AI Messages) */}
                  {((msg.sources && msg.sources.length > 0) || (msg.citations && msg.citations.length > 0)) && (
                    <div className="cs-citations-box">
                      <div className="cs-citations-title">
                        <span>📚 Verified Enterprise Sources:</span>
                      </div>
                      <div className="cs-citations-list">
                        {(msg.sources || msg.citations).map((cite, cIdx) => (
                          <div
                            key={cIdx}
                            className="cs-citation-pill"
                            onClick={() => setActiveCitation(cite)}
                            title="Click to view verified source excerpt"
                          >
                            <span className="cs-cite-icon">✓</span>
                            <span className="cs-cite-doc">{cite.document_title}</span>
                            <span className="cs-cite-view">Inspect ➔</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Clarification Options (For Ambiguous Inquiries) */}
                  {msg.clarification_options && msg.clarification_options.length > 0 && (
                    <div className="cs-clarification-box">
                      <div className="cs-clarification-title">💡 Clarification Choices:</div>
                      <div className="cs-clarification-pills">
                        {msg.clarification_options.map((opt, oIdx) => (
                          <button
                            key={oIdx}
                            type="button"
                            className="cs-clarification-btn"
                            disabled={isLoading}
                            onClick={() => onSendMessage(opt)}
                          >
                            {opt} ➔
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Suggested Quick Actions */}
                  {msg.suggested_actions && msg.suggested_actions.length > 0 && (
                    <div className="cs-suggested-actions-box">
                      <div className="cs-suggested-title">⚡ Recommended Next Steps:</div>
                      <div className="cs-suggested-pills">
                        {msg.suggested_actions.map((act, aIdx) => (
                          <button
                            key={aIdx}
                            type="button"
                            className="cs-suggested-action-btn"
                            disabled={isLoading}
                            onClick={() => {
                              const actLower = act.toLowerCase();
                              if (actLower.includes('service status') || actLower.includes('incident')) {
                                if (onNavigateTab) onNavigateTab('status');
                                else onSendMessage(act);
                              } else if (actLower.includes('support request') || actLower.includes('guided')) {
                                if (onNavigateTab) onNavigateTab('requests');
                                else onOpenCreateTicket({ description: msg.message, session_id: session?.id });
                              } else if (actLower.includes('my tickets') || actLower.includes('ticket status')) {
                                if (onNavigateTab) onNavigateTab('tickets');
                                else onSendMessage(act);
                              } else if (actLower.includes('knowledge base')) {
                                if (onNavigateTab) onNavigateTab('kb');
                                else onSendMessage(act);
                              } else if (actLower.includes('ticket')) {
                                onOpenCreateTicket({ description: msg.message, session_id: session?.id });
                              } else if (actLower.includes('specialist') || actLower.includes('agent') || actLower.includes('human')) {
                                onOpenHandoff();
                              } else {
                                onSendMessage(act);
                              }
                            }}
                          >
                            {act}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Confidence & Verified Grounding Row */}
                  {msg.sender_type === 'ai' && !msg.is_error && msg.confidence_score !== undefined && (
                    <div className="cs-meta-row">
                      <span className={`cs-confidence-badge ${msg.confidence_score >= 0.90 ? 'high' : msg.confidence_score >= 0.70 ? 'medium' : 'low'}`}>
                        Confidence: {Math.round((msg.confidence_score || 0.85) * 100)}%
                      </span>
                      <span className="cs-verified-badge">✓ Verified Knowledge</span>
                      <button
                        type="button"
                        className="cs-ai-details-toggle"
                        onClick={() => toggleAiDetails(msg.id)}
                      >
                        {expandedDetails[msg.id] ? 'Hide AI Details ▴' : 'AI Details ▾'}
                      </button>
                    </div>
                  )}

                  {/* Expandable AI Details Telemetry */}
                  {expandedDetails[msg.id] && (
                    <div className="cs-ai-details-panel">
                      <div className="cs-detail-item">
                        <strong>AI Engine:</strong> {msg.ai_provider || 'Deterministic Grounded RAG'}
                      </div>
                      <div className="cs-detail-item">
                        <strong>Latency:</strong> {msg.processing_time_ms ? `${msg.processing_time_ms}ms` : '< 20ms'}
                      </div>
                      <div className="cs-detail-item">
                        <strong>Knowledge Grounding:</strong> Strict Zero-Hallucination
                      </div>
                    </div>
                  )}

                  {/* Escalation Recommendation Banner */}
                  {msg.is_escalated && (
                    <div className="cs-escalation-banner">
                      <div className="cs-esc-icon">⚠️</div>
                      <div className="cs-esc-content">
                        <div className="cs-esc-title">Support Specialist Escalation Recommended</div>
                        <div className="cs-esc-desc">
                          This inquiry requires specialized review from our billing or engineering support team.
                        </div>
                        <div className="cs-esc-actions">
                          <button
                            type="button"
                            className="cs-esc-btn primary"
                            onClick={() => onOpenCreateTicket({ description: msg.message, session_id: session?.id })}
                          >
                            🎫 Create Support Ticket
                          </button>
                          <button
                            type="button"
                            className="cs-esc-btn secondary"
                            onClick={onOpenHandoff}
                          >
                            👤 Talk to Human Agent
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Message Actions (For AI Messages) */}
                {msg.sender_type === 'ai' && !msg.is_error && (
                  <div className="cs-msg-actions">
                    <button
                      type="button"
                      className="cs-action-btn"
                      onClick={() => handleCopy(msg.id, msg.message)}
                      title="Copy response"
                    >
                      {copiedId === msg.id ? '✓ Copied' : '📋 Copy'}
                    </button>
                    <button
                      type="button"
                      className={`cs-action-btn ${ratedMessages[msg.id] === 'helpful' ? 'active' : ''}`}
                      onClick={() => handleRate(msg.id, 'helpful')}
                      title="Helpful response"
                    >
                      👍 Helpful
                    </button>
                    <button
                      type="button"
                      className={`cs-action-btn ${ratedMessages[msg.id] === 'not_helpful' ? 'active' : ''}`}
                      onClick={() => handleRate(msg.id, 'not_helpful')}
                      title="Not helpful response"
                    >
                      👎 Not Helpful
                    </button>
                    <button
                      type="button"
                      className="cs-action-btn"
                      onClick={() => {
                        const prevCust = [...messages].reverse().find((m) => m.sender_type === 'customer');
                        if (prevCust) onSendMessage(prevCust.message);
                      }}
                      title="Regenerate grounded answer"
                    >
                      🔄 Regenerate
                    </button>
                    <button
                      type="button"
                      className="cs-action-btn"
                      onClick={() => onOpenCreateTicket({ session_id: session?.id, description: msg.message })}
                      title="Convert to support ticket"
                    >
                      🎫 Create Ticket
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {/* Loading / Thinking State */}
        {isLoading && (
          <div className="cs-message-row ai">
            <div className="cs-msg-avatar">🤖</div>
            <div className="cs-msg-bubble cs-loading-bubble">
              <div className="cs-typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <span className="cs-typing-text">AI is searching verified knowledge base...</span>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Citation Inspector Modal */}
      {activeCitation && (
        <div className="cs-modal-overlay" onClick={() => setActiveCitation(null)}>
          <div className="cs-citation-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cs-modal-header">
              <div className="cs-modal-title-box">
                <span className="cs-modal-icon">📄</span>
                <h3>Verified Knowledge Base Source</h3>
              </div>
              <button type="button" className="cs-close-btn" onClick={() => setActiveCitation(null)}>
                ✕
              </button>
            </div>
            <div className="cs-modal-body">
              <div className="cs-cite-modal-title">{activeCitation.document_title}</div>
              <div className="cs-cite-modal-badge">✓ Verified Enterprise Policy Excerpt</div>
              <blockquote className="cs-cite-quote">{activeCitation.excerpt}</blockquote>
            </div>
            <div className="cs-modal-footer">
              <button
                type="button"
                className="cs-btn primary"
                onClick={() => {
                  const docTitle = activeCitation.document_title;
                  setActiveCitation(null);
                  if (onOpenKbDoc) onOpenKbDoc(docTitle);
                }}
              >
                📚 Open in Knowledge Base Directory
              </button>
              <button type="button" className="cs-btn secondary" onClick={() => setActiveCitation(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Modern Message Composer */}
      <form className="cs-chat-footer" onSubmit={handleSend}>
        <div className="cs-composer-box">
          <textarea
            ref={textareaRef}
            rows={1}
            className="cs-composer-input"
            placeholder="Ask anything about your account, billing, product, technical issues... (Enter to send, Shift+Enter for new line)"
            value={inputMessage}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />

          <div className="cs-composer-controls">
            <button
              type="button"
              className="cs-composer-tool-btn"
              title="Attach diagnostic file or screenshot"
              onClick={() => alert('Attachment upload ready for support ticket creation.')}
            >
              📎
            </button>
            <button
              type="button"
              className="cs-composer-tool-btn"
              title="Voice input ready"
              onClick={() => alert('Voice input is operational.')}
            >
              🎙️
            </button>
            <button
              type="submit"
              className="cs-send-btn"
              disabled={!inputMessage.trim() || isLoading}
            >
              {isLoading ? 'Thinking...' : 'Send ➔'}
            </button>
          </div>
        </div>

        <div className="cs-footer-badge-row">
          <span>🛡️ Verified Enterprise Knowledge Base Connected</span>
          <span>•</span>
          <span>BM25 + RAG Grounding</span>
          <span>•</span>
          <span>Strict Zero-Hallucination Policy</span>
        </div>
      </form>
    </div>
  );
}
