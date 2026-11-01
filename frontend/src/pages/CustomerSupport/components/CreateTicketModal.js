/**
 * pages/CustomerSupport/components/CreateTicketModal.js
 *
 * Dedicated modal for creating enterprise support tickets:
 *   - Form fields: Subject, Category, Priority, Customer info, Description
 *   - Support for pre-filling from active chat session
 *   - Validation & submission handling
 */

import React, { useState } from 'react';

function currentUser() {
  try {
    return JSON.parse(localStorage.getItem('user')) || null;
  } catch {
    return null;
  }
}

export default function CreateTicketModal({
  initialData = {},
  categories = [],
  onClose,
  onSubmit,
}) {
  const me = currentUser();
  const defaultName = me?.full_name || 'Enterprise Customer';
  const defaultEmail = me?.email || 'customer@enterprise.ai';

  // Safely resolve category: if initialData.category_id matches a category id, use it;
  // otherwise fallback to first available category from the database
  const validInitialCatId = categories.some((c) => String(c.id) === String(initialData.category_id))
    ? initialData.category_id
    : (categories[0]?.id || '');

  const [subject, setSubject] = useState(initialData.subject || '');
  const [categoryId, setCategoryId] = useState(validInitialCatId);
  const [priority, setPriority] = useState(initialData.priority || 'medium');
  const [customerName, setCustomerName] = useState(initialData.customer_name || defaultName);
  const [customerEmail, setCustomerEmail] = useState(initialData.customer_email || defaultEmail);
  const [description, setDescription] = useState(initialData.description || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!subject.trim()) {
      setErrorMsg('Subject is required.');
      return;
    }
    if (!description.trim()) {
      setErrorMsg('Detailed problem description is required.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg('');

    try {
      await onSubmit({
        subject: subject.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        priority: priority,
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim(),
        description: description.trim(),
        session_id: initialData.session_id || null,
        channel: initialData.session_id ? 'chat' : 'web',
      });
      onClose();
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to create support ticket. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="cs-modal-overlay" onClick={onClose}>
      <div className="cs-create-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cs-modal-header">
          <div className="cs-modal-title-box">
            <span className="cs-modal-icon">🎫</span>
            <h3>Create Support Ticket</h3>
          </div>
          <button type="button" className="cs-close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="cs-modal-body">
            {errorMsg && <div className="cs-form-error">{errorMsg}</div>}

            <div className="cs-form-group">
              <label>Issue Subject *</label>
              <input
                type="text"
                placeholder="e.g., Unable to process refund on invoice #INV-204"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                required
              />
            </div>

            <div className="cs-form-row">
              <div className="cs-form-group">
                <label>Category</label>
                <select
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                >
                  <option value="">Select Category...</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="cs-form-group">
                <label>Priority Level</label>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                >
                  <option value="low">Low (Standard SLA 48h)</option>
                  <option value="medium">Medium (Standard SLA 24h)</option>
                  <option value="high">High (Priority SLA 4h)</option>
                  <option value="critical">Critical (Outage SLA 1h)</option>
                </select>
              </div>
            </div>

            <div className="cs-form-row">
              <div className="cs-form-group">
                <label>Customer Name</label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                />
              </div>

              <div className="cs-form-group">
                <label>Customer Email</label>
                <input
                  type="email"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="cs-form-group">
              <label>Detailed Problem Description *</label>
              <textarea
                rows={5}
                placeholder="Describe the issue, steps to reproduce, or diagnostic details..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
              />
            </div>

            {initialData.session_id && (
              <div className="cs-linked-note">
                🔗 Originating Chat Session: <code>{initialData.session_id}</code> will be linked for full context.
              </div>
            )}
          </div>

          <div className="cs-modal-footer">
            <button
              type="button"
              className="cs-btn secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="cs-btn primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Submitting Ticket...' : 'Submit Support Ticket'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
