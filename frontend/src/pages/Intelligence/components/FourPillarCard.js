/**
 * pages/Intelligence/components/FourPillarCard.js
 *
 * Renders an executive intelligence recommendation adhering to the
 * 4-pillar explainability framework:
 *   1. Observation
 *   2. Why This Matters
 *   3. Possible Future Consequence
 *   4. Recommended Preventive Action
 *
 * Prominently displays the advisory label and requires human review badge.
 */

import React from 'react';

const CATEGORY_ICONS = {
  project: '🎯',
  workload: '⚖️',
  incident: '🚨',
  support: '🎧',
  operations: '⚙️',
};

const URGENCY_BADGES = {
  low: { label: 'Low Urgency', cls: 'badge-muted' },
  medium: { label: 'Medium Urgency', cls: 'badge-amber' },
  high: { label: 'High Urgency', cls: 'badge-red' },
};

export default function FourPillarCard({ item }) {
  if (!item) return null;

  const {
    category,
    title,
    observation,
    why_it_matters,
    potential_consequence,
    recommended_preventive_action,
    urgency = 'medium',
  } = item;

  const icon = CATEGORY_ICONS[category?.toLowerCase()] || '💡';
  const urgencyBadge = URGENCY_BADGES[urgency?.toLowerCase()] || URGENCY_BADGES.medium;

  return (
    <div className="four-pillar-card">
      <div className="card-header">
        <div className="card-title-group">
          <span className="card-category-icon" aria-hidden="true">{icon}</span>
          <div>
            <h3 className="card-title">{title}</h3>
            <span className="card-category-name">{category ? category.toUpperCase() : 'GENERAL'}</span>
          </div>
        </div>
        <div className="card-badges">
          <span className={`intel-badge ${urgencyBadge.cls}`}>{urgencyBadge.label}</span>
          <span className="intel-badge badge-advisory" title="Requires human approval">Advisory Only</span>
        </div>
      </div>

      <div className="pillars-grid">
        {/* Pillar 1: Observation */}
        <div className="pillar-item pillar-observation">
          <div className="pillar-header">
            <span className="pillar-icon" aria-hidden="true">🔍</span>
            <span className="pillar-label">Observation</span>
          </div>
          <p className="pillar-body">{observation || 'No direct observation recorded.'}</p>
        </div>

        {/* Pillar 2: Why This Matters */}
        <div className="pillar-item pillar-why">
          <div className="pillar-header">
            <span className="pillar-icon" aria-hidden="true">💡</span>
            <span className="pillar-label">Why This Matters</span>
          </div>
          <p className="pillar-body">{why_it_matters || 'Impact assessment pending.'}</p>
        </div>

        {/* Pillar 3: Possible Future Consequence */}
        <div className="pillar-item pillar-consequence">
          <div className="pillar-header">
            <span className="pillar-icon" aria-hidden="true">⚠️</span>
            <span className="pillar-label">Possible Future Consequence</span>
          </div>
          <p className="pillar-body">{potential_consequence || 'Risks remain contained if addressed promptly.'}</p>
        </div>

        {/* Pillar 4: Recommended Preventive Action */}
        <div className="pillar-item pillar-action">
          <div className="pillar-header">
            <span className="pillar-icon" aria-hidden="true">🛡️</span>
            <span className="pillar-label">Recommended Preventive Action</span>
          </div>
          <p className="pillar-body">{recommended_preventive_action || 'Review metrics with project leads.'}</p>
        </div>
      </div>

      <div className="card-footer-notice">
        <span className="notice-icon" aria-hidden="true">ℹ️</span>
        <span>Advisory recommendation only. No automated business actions are executed.</span>
      </div>
    </div>
  );
}
