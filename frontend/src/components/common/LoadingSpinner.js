import React from 'react';
import './LoadingSpinner.css';

/** Small inline spinner + label, for panel/section loading states. */
export default function LoadingSpinner({ label = 'Loading…', size = 20 }) {
  return (
    <div className="loading-spinner-row" role="status" aria-live="polite">
      <span className="loading-spinner" style={{ width: size, height: size }} aria-hidden="true" />
      {label && <span className="loading-spinner-label">{label}</span>}
    </div>
  );
}
