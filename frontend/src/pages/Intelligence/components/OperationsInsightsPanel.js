/**
 * pages/Intelligence/components/OperationsInsightsPanel.js
 *
 * Cross-module Operations Intelligence view (Admin & Manager only).
 * Synthesizes customer support friction points, recurring incident vulnerability patterns,
 * and strategic operational improvements.
 */

import React from 'react';

export default function OperationsInsightsPanel({ data }) {
  if (!data) {
    return (
      <div className="intel-empty-card">
        <p>No operational insights available at this time.</p>
      </div>
    );
  }

  const { support_insights = [], incident_insights = [], operational_summary, metadata } = data;

  return (
    <div className="operations-insights-panel">
      <div className="panel-intro-header">
        <div>
          <h3>Cross-Module Operational Intelligence</h3>
          <p className="section-subtext">
            Synthesizes support ticket trends and infrastructure incidents to uncover recurring
            customer friction points and systemic vulnerabilities.
          </p>
        </div>
      </div>

      {/* Operational Strategic Summary */}
      <div className="ops-summary-card">
        <div className="ops-summary-header">
          <span className="ops-icon" aria-hidden="true">🌐</span>
          <h4>Operational Synthesis & Strategic Summary</h4>
        </div>
        <p className="ops-summary-text">{operational_summary || 'No operational summary recorded.'}</p>
        
        {metadata && (
          <div className="brief-metadata">
            <span><strong>Model:</strong> {metadata.model_name || metadata.model_provider}</span>
            <span><strong>Generated:</strong> {metadata.generated_at ? new Date(metadata.generated_at).toLocaleString() : 'Just now'}</span>
            {metadata.is_cached && <span className="meta-badge cached">Cached Result</span>}
            {metadata.is_fallback && <span className="meta-badge fallback">Rule Engine Fallback</span>}
          </div>
        )}
      </div>

      {/* Two Column Layout: Support vs Incidents */}
      <div className="ops-columns-grid">
        {/* Customer Support Insights */}
        <div className="ops-column-card">
          <div className="column-header support-header">
            <span className="column-icon" aria-hidden="true">🎧</span>
            <div>
              <h4>Customer Support Intelligence</h4>
              <span className="column-subtext">Friction categories & ticket escalations</span>
            </div>
          </div>
          {support_insights.length === 0 ? (
            <p className="ops-empty-text">No significant customer support friction patterns detected.</p>
          ) : (
            <ul className="ops-insights-list">
              {support_insights.map((insight, idx) => (
                <li key={idx} className="insight-item">
                  <span className="insight-bullet" aria-hidden="true">📌</span>
                  <span className="insight-text">{insight}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Incident Vulnerability Insights */}
        <div className="ops-column-card">
          <div className="column-header incident-header">
            <span className="column-icon" aria-hidden="true">🚨</span>
            <div>
              <h4>Incident Vulnerability Patterns</h4>
              <span className="column-subtext">System reliability & outage root causes</span>
            </div>
          </div>
          {incident_insights.length === 0 ? (
            <p className="ops-empty-text">No recurring critical incident vulnerabilities detected.</p>
          ) : (
            <ul className="ops-insights-list">
              {incident_insights.map((insight, idx) => (
                <li key={idx} className="insight-item">
                  <span className="insight-bullet" aria-hidden="true">⚠️</span>
                  <span className="insight-text">{insight}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card-advisory-tag">
        <span>Advisory operational synthesis. Changes to SLAs, workflows, or infrastructure require human executive authorization.</span>
      </div>
    </div>
  );
}
