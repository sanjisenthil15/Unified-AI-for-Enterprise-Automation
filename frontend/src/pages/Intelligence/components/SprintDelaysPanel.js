/**
 * pages/Intelligence/components/SprintDelaysPanel.js
 *
 * Sprint Delay Intelligence view.
 * Grounded in actual sprint timelines and completion ratios.
 * Highlights delay statuses: ON_TRACK, AT_RISK, DELAYED, and explicitly INSUFFICIENT_DATA.
 */

import React from 'react';

const STATUS_CONFIG = {
  on_track: {
    label: 'ON TRACK',
    icon: '✅',
    cls: 'status-badge-on-track',
    cardCls: 'card-border-green',
  },
  at_risk: {
    label: 'AT RISK',
    icon: '⚠️',
    cls: 'status-badge-at-risk',
    cardCls: 'card-border-amber',
  },
  delayed: {
    label: 'DELAYED',
    icon: '🚨',
    cls: 'status-badge-delayed',
    cardCls: 'card-border-red',
  },
  insufficient_data: {
    label: 'INSUFFICIENT DATA',
    icon: 'ℹ️',
    cls: 'status-badge-insufficient',
    cardCls: 'card-border-gray',
  },
};

export default function SprintDelaysPanel({ data }) {
  const sprints = data?.sprints || [];

  if (sprints.length === 0) {
    return (
      <div className="intel-empty-card">
        <p>No active or recent sprints found for this project scope.</p>
      </div>
    );
  }

  return (
    <div className="sprint-delays-panel">
      <div className="panel-intro-header">
        <div>
          <h3>Sprint Timeline & Delivery Trajectories</h3>
          <p className="section-subtext">
            Delay risk classifications are computed strictly from verified task completion rates,
            elapsed sprint duration, and overdue deliverables. No speculative completion dates are fabricated.
          </p>
        </div>
      </div>

      <div className="sprints-grid">
        {sprints.map((sprint) => {
          const statusKey = (sprint.delay_status || 'on_track').toLowerCase();
          const config = STATUS_CONFIG[statusKey] || STATUS_CONFIG.insufficient_data;

          return (
            <div key={sprint.sprint_id} className={`sprint-card ${config.cardCls}`}>
              <div className="sprint-header">
                <div>
                  <h4 className="sprint-name">{sprint.sprint_name}</h4>
                  <span className="sprint-project">{sprint.project_name}</span>
                </div>
                <div className="sprint-status-wrap">
                  <span className={`sprint-badge ${config.cls}`}>
                    <span className="badge-icon" aria-hidden="true">{config.icon}</span>
                    {config.label}
                  </span>
                </div>
              </div>

              {/* Status Explanation */}
              <div className="sprint-explanation">
                <span className="box-title">Trajectory Assessment:</span>
                <p className="box-text">{sprint.delay_explanation}</p>
              </div>

              {/* Contributing Factors */}
              {sprint.contributing_factors && sprint.contributing_factors.length > 0 && (
                <div className="sprint-factors">
                  <span className="box-title">Contributing Factors:</span>
                  <ul className="factors-list">
                    {sprint.contributing_factors.map((factor, idx) => (
                      <li key={idx}>{factor}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Recommended Mitigations */}
              {sprint.recommended_mitigations && sprint.recommended_mitigations.length > 0 && (
                <div className="sprint-mitigations">
                  <span className="box-title">Recommended Mitigations:</span>
                  <ul className="mitigations-list">
                    {sprint.recommended_mitigations.map((mit, idx) => (
                      <li key={idx}>{mit}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="card-advisory-tag">
                <span>Advisory recommendation only. Requires human review by sprint leaders.</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
