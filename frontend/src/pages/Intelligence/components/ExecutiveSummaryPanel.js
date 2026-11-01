/**
 * pages/Intelligence/components/ExecutiveSummaryPanel.js
 *
 * Executive Intelligence Summary view for Admin & Manager.
 * Displays overall organization health, executive brief, metadata,
 * and structured 4-pillar actionable recommendations.
 */

import React from 'react';
import FourPillarCard from './FourPillarCard';

const HEALTH_STATUS_CONFIG = {
  healthy: {
    label: 'Healthy Operations',
    icon: '✅',
    cls: 'status-healthy',
    description: 'Enterprise operations, delivery trajectories, and support queues are functioning within normal bounds.',
  },
  attention_required: {
    label: 'Attention Required',
    icon: '⚠️',
    cls: 'status-attention',
    description: 'Early friction detected in project timelines or resource distribution that warrants managerial attention.',
  },
  critical_attention: {
    label: 'Critical Attention Required',
    icon: '🚨',
    cls: 'status-critical',
    description: 'Multiple projects or critical incidents exceed risk thresholds. Immediate leadership review recommended.',
  },
};

export default function ExecutiveSummaryPanel({ data }) {
  if (!data) {
    return (
      <div className="intel-empty-card">
        <p>No executive summary data available. Click Refresh to analyze enterprise operations.</p>
      </div>
    );
  }

  const { overall_status = 'healthy', executive_brief, recommendations = [], metadata } = data;
  const statusConfig = HEALTH_STATUS_CONFIG[overall_status.toLowerCase()] || HEALTH_STATUS_CONFIG.healthy;

  return (
    <div className="executive-summary-panel">
      {/* Top Health & Brief Banner */}
      <div className={`health-banner ${statusConfig.cls}`}>
        <div className="health-header">
          <div className="health-icon" aria-hidden="true">{statusConfig.icon}</div>
          <div>
            <div className="health-status-badge">{statusConfig.label}</div>
            <h2 className="health-title">Organization Health Assessment</h2>
            <p className="health-description">{statusConfig.description}</p>
          </div>
        </div>
      </div>

      {/* Executive Brief Card */}
      <div className="brief-card">
        <div className="brief-header">
          <span className="brief-icon" aria-hidden="true">📋</span>
          <h3>Executive Briefing</h3>
        </div>
        <p className="brief-text">{executive_brief || 'No briefing available.'}</p>
        
        {metadata && (
          <div className="brief-metadata">
            <span><strong>Model:</strong> {metadata.model_name || metadata.model_provider}</span>
            <span><strong>Generated:</strong> {metadata.generated_at ? new Date(metadata.generated_at).toLocaleString() : 'Just now'}</span>
            {metadata.is_cached && <span className="meta-badge cached">Cached Result</span>}
            {metadata.is_fallback && <span className="meta-badge fallback">Rule Engine Fallback</span>}
          </div>
        )}
      </div>

      {/* Actionable Recommendations Section */}
      <div className="recommendations-section">
        <div className="section-title-wrap">
          <span className="section-icon" aria-hidden="true">💡</span>
          <div>
            <h3>Actionable Executive Recommendations</h3>
            <p className="section-subtext">Ground truth analysis synthesized across projects, sprints, incidents, and support metrics.</p>
          </div>
        </div>

        {recommendations.length === 0 ? (
          <div className="intel-empty-card">
            <p>No high-risk operational anomalies detected at this time.</p>
          </div>
        ) : (
          <div className="recommendations-list">
            {recommendations.map((rec) => (
              <FourPillarCard key={rec.id} item={rec} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
