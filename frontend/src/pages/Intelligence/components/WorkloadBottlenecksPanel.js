/**
 * pages/Intelligence/components/WorkloadBottlenecksPanel.js
 *
 * Workload Bottlenecks view.
 * Displays role-level workload imbalances, severity levels,
 * affected role categories (anonymized, no individual worker surveillance),
 * and suggested rebalancing actions.
 */

import React from 'react';

const SEVERITY_CONFIG = {
  low: { label: 'Low Severity', cls: 'sev-badge-low', barCls: 'bar-low' },
  medium: { label: 'Medium Severity', cls: 'sev-badge-medium', barCls: 'bar-medium' },
  high: { label: 'High Severity', cls: 'sev-badge-high', barCls: 'bar-high' },
};

export default function WorkloadBottlenecksPanel({ data }) {
  const bottlenecks = data?.bottlenecks || [];

  if (bottlenecks.length === 0) {
    return (
      <div className="intel-empty-card">
        <p>No workload bottlenecks or severe allocation imbalances detected in this scope.</p>
      </div>
    );
  }

  return (
    <div className="workload-bottlenecks-panel">
      <div className="panel-intro-header">
        <div>
          <h3>Team & Role Workload Distribution</h3>
          <p className="section-subtext">
            Detects operational imbalances, role overloading, and underutilized capacity without
            exposing individual worker surveillance or subjective productivity ratings.
          </p>
        </div>
      </div>

      <div className="bottlenecks-grid">
        {bottlenecks.map((item, idx) => {
          const sevKey = (item.bottleneck_severity || 'medium').toLowerCase();
          const sevConfig = SEVERITY_CONFIG[sevKey] || SEVERITY_CONFIG.medium;

          return (
            <div key={idx} className="bottleneck-card">
              <div className="card-top-bar">
                <div>
                  <h4 className="bottleneck-title">{item.team_or_project}</h4>
                  <span className="card-sub-label">Team / Project Scope</span>
                </div>
                <div>
                  <span className={`intel-badge ${sevConfig.cls}`}>{sevConfig.label}</span>
                </div>
              </div>

              {/* Observation */}
              <div className="bottleneck-box">
                <span className="box-title">🔍 Allocation Observation:</span>
                <p className="box-text">{item.observation}</p>
              </div>

              {/* Affected Roles */}
              {item.affected_roles && item.affected_roles.length > 0 && (
                <div className="roles-section">
                  <span className="box-title">Affected Roles:</span>
                  <div className="roles-tags">
                    {item.affected_roles.map((r, rIdx) => (
                      <span key={rIdx} className="role-tag">
                        👤 {r}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Rebalancing Recommendation */}
              <div className="rebalancing-box">
                <span className="box-title">⚖️ Suggested Balancing Action:</span>
                <p className="box-text">{item.suggested_balancing_action}</p>
              </div>

              <div className="card-advisory-tag">
                <span>Advisory suggestion only. Workload reallocations require team lead or manager approval.</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
