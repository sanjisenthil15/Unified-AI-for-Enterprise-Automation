/**
 * pages/CustomerSupport/components/SupportRequestsView.js
 *
 * Enterprise Guided Support Request Center.
 * Features:
 *   - 6-step guided wizard (Area -> Type -> Details -> Attachments -> AI Pre-Analysis -> Submit)
 *   - AI Pre-submission Analysis (detected category, recommended team, priority, summary, relevant KB doc)
 *   - Real-time Duplicate Request Detection (checks active open tickets)
 *   - Direct submission to existing SupportTicket infrastructure
 */

import React, { useState } from 'react';
import { analyzeSupportRequest } from '../../../api/customerSupportApi';

const ISSUE_AREAS = [
  { id: 1, name: 'Billing & Payments', icon: '💳', desc: 'Refunds, duplicate charges, payment failures, invoice inquiries' },
  { id: 2, name: 'Account & Security', icon: '🔐', desc: 'Password reset, 2FA/MFA setup, locked accounts, active sessions' },
  { id: 3, name: 'Technical & API Support', icon: '⚙️', desc: 'HTTP 500/404/401 errors, API timeouts, backend request failures' },
  { id: 4, name: 'Subscriptions & Invoicing', icon: '📦', desc: 'Plan upgrades, renewals, ₹999 recharge activations, license sync' },
  { id: 5, name: 'UI & Dashboard', icon: '🛠️', desc: 'Unresponsive buttons, browser cache, dashboard rendering defects' },
  { id: 6, name: 'General & Other', icon: '📋', desc: 'Service requests, general platform questions, specialist escalation' },
];

const PRESET_ISSUES = {
  1: [
    'Money deducted for recharge but service not activated',
    'Charged twice for annual enterprise subscription',
    'Payment failed but card shows pending deduction',
    'Request full refund within 30-day policy period',
    'Need updated payment invoice / receipt',
  ],
  2: [
    'Account locked after multiple login attempts',
    'Lost 2FA authenticator device and need backup access',
    'Password reset link not received in enterprise email',
    'Sign out from all remote active sessions',
    'Suspicious unauthorized access alert on account',
  ],
  3: [
    'API endpoint returning HTTP 500 Internal Server Error',
    'HTTP 401 Unauthorized error with valid Bearer token',
    'REST API timeout (>10s) on batch candidate processing',
    'Rate limit exceeded (HTTP 429) during normal business load',
    'Webhook delivery failure for payment event notifications',
  ],
  4: [
    'I paid ₹999 but my data plan is still inactive',
    'Upgrade subscription from Starter to Enterprise tier',
    'Downgrade plan at end of current billing cycle',
    'Subscription renewal failed with active card on file',
    'License count reconciliation for team members',
  ],
  5: [
    'Dashboard action buttons unresponsive after click',
    'Clearing cache and hard refresh did not resolve page freeze',
    'Table pagination not loading next page of records',
    'Interface displaying layout distortion on Edge / Chrome',
  ],
  6: [
    'Request dedicated enterprise support engineer assistance',
    'SLA escalation for unresolved critical inquiry',
    'General product feature inquiry',
    'Enterprise integration consultation request',
  ],
};

export default function SupportRequestsView({
  categories = [],
  onSubmitTicket,
  onViewTicket,
  onAskAi,
}) {
  const [currentStep, setCurrentStep] = useState(1);
  const [selectedAreaId, setSelectedAreaId] = useState(1);
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [customerName, setCustomerName] = useState('Enterprise Admin');
  const [customerEmail, setCustomerEmail] = useState('admin@enterprise.ai');
  const [referenceId, setReferenceId] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [priority, setPriority] = useState('medium');

  // AI Pre-Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedTicket, setSubmittedTicket] = useState(null);

  function handleSelectArea(areaId) {
    setSelectedAreaId(areaId);
    setCurrentStep(2);
  }

  function handleSelectPresetIssue(issueText) {
    setSubject(issueText);
    setCurrentStep(3);
  }

  function handleFileUpload(e) {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      const mapped = files.map((f) => ({
        name: f.name,
        size: `${(f.size / 1024).toFixed(1)} KB`,
        type: f.type || 'application/octet-stream',
      }));
      setAttachments((prev) => [...prev, ...mapped]);
    }
  }

  function handleRemoveAttachment(idx) {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleProceedToAnalysis() {
    if (!subject.trim() || !description.trim()) {
      alert('Please provide both an issue summary and a detailed description.');
      return;
    }

    setIsAnalyzing(true);
    setCurrentStep(5);

    try {
      const analysis = await analyzeSupportRequest({
        subject: subject.trim(),
        description: description.trim(),
        category_id: selectedAreaId,
        customer_email: customerEmail.trim(),
      });
      setAiAnalysis(analysis);
      if (analysis.suggested_priority) {
        setPriority(analysis.suggested_priority);
      }
    } catch (err) {
      console.warn('AI analysis fallback:', err);
      setAiAnalysis({
        detected_issue: subject,
        detected_category: ISSUE_AREAS.find((a) => a.id === selectedAreaId)?.name || 'General Support',
        category_id: selectedAreaId,
        recommended_team: 'General Customer Support Team',
        suggested_priority: 'medium',
        ai_summary: description.slice(0, 150) + '...',
        relevant_knowledge_title: 'Enterprise Support Workflow & SLA Guide',
        relevant_knowledge_excerpt: 'Our support teams monitor enterprise tickets 24/7.',
        duplicate_alert: null,
      });
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleFinalSubmit() {
    setIsSubmitting(true);
    try {
      const ticketPayload = {
        subject: subject.trim(),
        description: description.trim() + (referenceId ? `\n\nReference / Transaction ID: ${referenceId}` : ''),
        category_id: aiAnalysis?.category_id || selectedAreaId || 1,
        priority: priority || aiAnalysis?.suggested_priority || 'medium',
        channel: 'web',
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim(),
      };

      if (onSubmitTicket) {
        const created = await onSubmitTicket(ticketPayload);
        setSubmittedTicket(created || { id: 1004, ...ticketPayload, status: 'open' });
        setCurrentStep(6);
      }
    } catch (err) {
      alert('Error creating support ticket. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleReset() {
    setCurrentStep(1);
    setSelectedAreaId(1);
    setSubject('');
    setDescription('');
    setReferenceId('');
    setAttachments([]);
    setAiAnalysis(null);
    setSubmittedTicket(null);
  }

  return (
    <div className="cs-requests-view-container">
      {/* Wizard Progress Stepper */}
      <div className="cs-wizard-stepper">
        {[
          { step: 1, label: '1. Issue Area' },
          { step: 2, label: '2. Issue Type' },
          { step: 3, label: '3. Details' },
          { step: 4, label: '4. Attachments' },
          { step: 5, label: '5. AI Analysis' },
          { step: 6, label: '6. Confirmation' },
        ].map((s) => (
          <div
            key={s.step}
            className={`cs-step-indicator ${currentStep === s.step ? 'active' : currentStep > s.step ? 'completed' : ''}`}
          >
            <div className="cs-step-circle">
              {currentStep > s.step ? '✓' : s.step}
            </div>
            <span className="cs-step-text">{s.label}</span>
          </div>
        ))}
      </div>

      {/* STEP 1: Select Issue Area */}
      {currentStep === 1 && (
        <div className="cs-wizard-card">
          <div className="cs-wizard-header">
            <h2>Step 1: Select Your Support Issue Area</h2>
            <p>Choose the category that best represents your enterprise support inquiry.</p>
          </div>

          <div className="cs-areas-grid">
            {ISSUE_AREAS.map((area) => (
              <div
                key={area.id}
                className={`cs-area-card ${selectedAreaId === area.id ? 'selected' : ''}`}
                onClick={() => handleSelectArea(area.id)}
              >
                <div className="cs-area-icon">{area.icon}</div>
                <h3 className="cs-area-title">{area.name}</h3>
                <p className="cs-area-desc">{area.desc}</p>
                <button type="button" className="cs-area-select-btn">
                  Select Area ➔
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* STEP 2: Issue Type & Preset Selection */}
      {currentStep === 2 && (
        <div className="cs-wizard-card">
          <div className="cs-wizard-header">
            <button type="button" className="cs-back-link" onClick={() => setCurrentStep(1)}>
              ← Back to Issue Areas
            </button>
            <h2>Step 2: What is the specific issue?</h2>
            <p>Select a common issue below or enter a custom subject summary.</p>
          </div>

          <div className="cs-presets-list">
            {(PRESET_ISSUES[selectedAreaId] || []).map((preset, pIdx) => (
              <button
                key={pIdx}
                type="button"
                className="cs-preset-btn"
                onClick={() => handleSelectPresetIssue(preset)}
              >
                <span className="cs-preset-text">{preset}</span>
                <span className="cs-preset-arrow">➔</span>
              </button>
            ))}
          </div>

          <div className="cs-custom-subject-box">
            <label className="cs-form-label">Or enter custom subject summary:</label>
            <div className="cs-input-action-row">
              <input
                type="text"
                className="cs-form-input"
                placeholder="e.g. Data plan not active after ₹999 payment deduction"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
              />
              <button
                type="button"
                className="cs-btn primary"
                disabled={!subject.trim()}
                onClick={() => setCurrentStep(3)}
              >
                Continue ➔
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STEP 3: Enter Details & Description */}
      {currentStep === 3 && (
        <div className="cs-wizard-card">
          <div className="cs-wizard-header">
            <button type="button" className="cs-back-link" onClick={() => setCurrentStep(2)}>
              ← Back to Issue Type
            </button>
            <h2>Step 3: Provide Problem Details & Impact</h2>
            <p>The more detail you provide, the faster our AI and specialists can resolve it.</p>
          </div>

          <div className="cs-form-stack">
            <div className="cs-form-group">
              <label className="cs-form-label">Issue Subject *</label>
              <input
                type="text"
                className="cs-form-input"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                required
              />
            </div>

            <div className="cs-form-group">
              <label className="cs-form-label">Detailed Description & Error Logs *</label>
              <textarea
                rows={5}
                className="cs-form-textarea"
                placeholder="Explain what occurred, transaction dates, error messages received, and expected behavior..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
              />
            </div>

            <div className="cs-form-row-2">
              <div className="cs-form-group">
                <label className="cs-form-label">Customer Name</label>
                <input
                  type="text"
                  className="cs-form-input"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                />
              </div>

              <div className="cs-form-group">
                <label className="cs-form-label">Enterprise Email *</label>
                <input
                  type="email"
                  className="cs-form-input"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="cs-form-group">
              <label className="cs-form-label">Transaction ID / Invoice / API Endpoint (Optional)</label>
              <input
                type="text"
                className="cs-form-input"
                placeholder="e.g. TXN-999-RECHARGE or /api/v1/recruitment/candidates"
                value={referenceId}
                onChange={(e) => setReferenceId(e.target.value)}
              />
            </div>

            <div className="cs-wizard-actions">
              <button type="button" className="cs-btn secondary" onClick={() => setCurrentStep(2)}>
                Back
              </button>
              <button
                type="button"
                className="cs-btn primary"
                disabled={!subject.trim() || !description.trim()}
                onClick={() => setCurrentStep(4)}
              >
                Next: Attachments ➔
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STEP 4: Attachments */}
      {currentStep === 4 && (
        <div className="cs-wizard-card">
          <div className="cs-wizard-header">
            <button type="button" className="cs-back-link" onClick={() => setCurrentStep(3)}>
              ← Back to Details
            </button>
            <h2>Step 4: Attach Diagnostic Files or Screenshots (Optional)</h2>
            <p>Attach invoices, error screenshots, PDF receipts, or log dumps.</p>
          </div>

          <div className="cs-upload-dropzone">
            <input
              type="file"
              id="file-upload"
              multiple
              className="cs-file-input"
              onChange={handleFileUpload}
            />
            <label htmlFor="file-upload" className="cs-dropzone-label">
              <div className="cs-dropzone-icon">📁</div>
              <div className="cs-dropzone-title">Click to upload or drag files here</div>
              <div className="cs-dropzone-hint">PNG, JPG, PDF, TXT, JSON up to 10MB</div>
            </label>
          </div>

          {attachments.length > 0 && (
            <div className="cs-attachments-list">
              <h4>Attached Files ({attachments.length}):</h4>
              {attachments.map((file, fIdx) => (
                <div key={fIdx} className="cs-attachment-item">
                  <span className="cs-attach-icon">📎</span>
                  <span className="cs-attach-name">{file.name}</span>
                  <span className="cs-attach-size">({file.size})</span>
                  <button
                    type="button"
                    className="cs-attach-remove"
                    onClick={() => handleRemoveAttachment(fIdx)}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="cs-wizard-actions">
            <button type="button" className="cs-btn secondary" onClick={() => setCurrentStep(3)}>
              Back
            </button>
            <button
              type="button"
              className="cs-btn primary"
              onClick={handleProceedToAnalysis}
            >
              Analyze with AI & Review ➔
            </button>
          </div>
        </div>
      )}

      {/* STEP 5: AI-Assisted Pre-Submission Analysis & Duplicate Check */}
      {currentStep === 5 && (
        <div className="cs-wizard-card">
          <div className="cs-wizard-header">
            <button type="button" className="cs-back-link" onClick={() => setCurrentStep(4)}>
              ← Back to Attachments
            </button>
            <h2>Step 5: AI Pre-Submission Analysis & Verification</h2>
            <p>Our autonomous triage engine analyzed your request before ticket assignment.</p>
          </div>

          {isAnalyzing ? (
            <div className="cs-loading-state">
              <div className="cs-spinner"></div>
              <span>AI Triage is classifying issue domain and scanning for duplicates...</span>
            </div>
          ) : (
            <div className="cs-ai-analysis-container">
              {/* Duplicate Request Detection Alert */}
              {aiAnalysis?.duplicate_alert && (
                <div className="cs-duplicate-alert-banner">
                  <div className="cs-dup-icon">⚠️</div>
                  <div className="cs-dup-content">
                    <div className="cs-dup-title">Similar Open Support Request Detected</div>
                    <div className="cs-dup-desc">
                      You already have an active request: <strong>Ticket #{aiAnalysis.duplicate_alert.ticket_id}</strong> -{' '}
                      <em>"{aiAnalysis.duplicate_alert.subject}"</em> ({aiAnalysis.duplicate_alert.status})
                    </div>
                    <div className="cs-dup-actions">
                      <button
                        type="button"
                        className="cs-btn secondary"
                        onClick={() => onViewTicket && onViewTicket(aiAnalysis.duplicate_alert.ticket_id)}
                      >
                        👁️ View Existing Ticket #{aiAnalysis.duplicate_alert.ticket_id}
                      </button>
                      <span className="cs-dup-hint">Or continue below to submit a separate request.</span>
                    </div>
                  </div>
                </div>
              )}

              {/* AI Analysis Cards Grid */}
              <div className="cs-analysis-grid">
                <div className="cs-analysis-card">
                  <div className="cs-analysis-card-label">🤖 Detected Issue Domain</div>
                  <div className="cs-analysis-card-val">{aiAnalysis?.detected_category}</div>
                </div>

                <div className="cs-analysis-card">
                  <div className="cs-analysis-card-label">👥 Recommended Resolution Team</div>
                  <div className="cs-analysis-card-val blue">{aiAnalysis?.recommended_team}</div>
                </div>

                <div className="cs-analysis-card">
                  <div className="cs-analysis-card-label">⚡ Suggested Priority Level</div>
                  <div className="cs-priority-selector-row">
                    {['low', 'medium', 'high', 'critical'].map((p) => (
                      <button
                        key={p}
                        type="button"
                        className={`cs-priority-chip ${p} ${priority === p ? 'active' : ''}`}
                        onClick={() => setPriority(p)}
                      >
                        {p.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="cs-analysis-card full">
                  <div className="cs-analysis-card-label">📝 AI Executive Summary</div>
                  <p className="cs-ai-summary-text">{aiAnalysis?.ai_summary}</p>
                </div>
              </div>

              {/* Relevant Knowledge Self-Service Callout */}
              {aiAnalysis?.relevant_knowledge_title && (
                <div className="cs-kb-suggestion-card">
                  <div className="cs-kb-sug-header">
                    <span className="cs-kb-sug-icon">📚</span>
                    <div>
                      <h4>Instant Resolution Knowledge Base Article</h4>
                      <span className="cs-kb-sug-title">{aiAnalysis.relevant_knowledge_title}</span>
                    </div>
                  </div>
                  <p className="cs-kb-sug-excerpt">{aiAnalysis.relevant_knowledge_excerpt}</p>
                  <button
                    type="button"
                    className="cs-btn secondary small"
                    onClick={() => onAskAi && onAskAi(`Tell me about: ${aiAnalysis.relevant_knowledge_title}`)}
                  >
                    Ask AI Assistant About This Policy ➔
                  </button>
                </div>
              )}

              {/* Final Submission Action */}
              <div className="cs-wizard-actions">
                <button type="button" className="cs-btn secondary" onClick={() => setCurrentStep(4)}>
                  Back
                </button>
                <button
                  type="button"
                  className="cs-btn primary"
                  disabled={isSubmitting}
                  onClick={handleFinalSubmit}
                >
                  {isSubmitting ? 'Creating Ticket...' : '✓ Submit Support Request'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* STEP 6: Confirmation & Created Ticket Summary */}
      {currentStep === 6 && submittedTicket && (
        <div className="cs-wizard-card success-card">
          <div className="cs-success-hero">
            <div className="cs-success-icon">✓</div>
            <h2>Support Request Submitted Successfully!</h2>
            <p>Your request has been registered in the enterprise ticketing system and assigned to specialists.</p>
          </div>

          <div className="cs-submitted-ticket-summary">
            <div className="cs-summary-row">
              <span>Request / Ticket ID:</span>
              <strong className="cs-ticket-badge">#TKT-{submittedTicket.id}</strong>
            </div>
            <div className="cs-summary-row">
              <span>Subject:</span>
              <strong>{submittedTicket.subject}</strong>
            </div>
            <div className="cs-summary-row">
              <span>Assigned Team:</span>
              <strong className="cs-team-tag">{aiAnalysis?.recommended_team || 'Billing & Finance Team'}</strong>
            </div>
            <div className="cs-summary-row">
              <span>Priority:</span>
              <span className={`cs-priority-tag ${submittedTicket.priority}`}>{submittedTicket.priority.toUpperCase()}</span>
            </div>
            <div className="cs-summary-row">
              <span>Target SLA Response:</span>
              <strong className="green">
                {submittedTicket.priority === 'critical' ? '< 1 Hour (24/7)' : submittedTicket.priority === 'high' ? '< 4 Hours' : '< 24 Hours'}
              </strong>
            </div>
          </div>

          <div className="cs-wizard-actions center">
            <button
              type="button"
              className="cs-btn primary"
              onClick={() => onViewTicket && onViewTicket(submittedTicket.id)}
            >
              🎫 View Ticket Tracking Thread
            </button>
            <button type="button" className="cs-btn secondary" onClick={handleReset}>
              Create Another Request
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
