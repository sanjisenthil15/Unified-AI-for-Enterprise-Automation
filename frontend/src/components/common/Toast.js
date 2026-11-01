import React from 'react';
import './Toast.css';

/**
 * Toast notification component.
 * Supports 'success', 'error', and 'info' types with animated entry/exit and icons.
 */
export default function Toast({ message, type = 'success', onClose }) {
  if (!message) return null;

  return (
    <div className={`app-toast app-toast-${type}`} role="alert" aria-live="polite">
      <div className="toast-icon-container">
        {type === 'success' && (
          <svg className="toast-svg-icon toast-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
        {type === 'error' && (
          <svg className="toast-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="10" strokeWidth="2" />
            <line x1="12" y1="8" x2="12" y2="12" strokeWidth="2" strokeLinecap="round" />
            <line x1="12" y1="16" x2="12.01" y2="16" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        )}
        {type === 'info' && (
          <svg className="toast-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <circle cx="12" cy="12" r="10" strokeWidth="2" />
            <line x1="12" y1="16" x2="12" y2="12" strokeWidth="2" strokeLinecap="round" />
            <line x1="12" y1="8" x2="12.01" y2="8" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        )}
      </div>
      <div className="toast-body">
        <span className="toast-message">{message}</span>
      </div>
      {onClose && (
        <button
          type="button"
          className="toast-close-btn"
          onClick={onClose}
          aria-label="Dismiss notification"
        >
          ×
        </button>
      )}
    </div>
  );
}

