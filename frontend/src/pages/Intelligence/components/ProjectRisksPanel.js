/**
 * pages/Intelligence/components/ProjectRisksPanel.js
 *
 * Project Risk Intelligence view.
 * Displays deterministic risk scores calculated by the backend rule engine,
 * risk levels (LOW, MEDIUM, HIGH), contributing risk factors,
 * root-cause explanations, and recommended preventive actions.
 */

import React from 'react';

const RISK_LEVEL_CONFIG = {
  low: { label: 'LOW RISK', cls: 'risk-badge-low', barCls: 'bar-low' },
  medium: { label: 'MEDIUM RISK', cls: 'risk-badge-medium', barCls: 'bar-medium' },
  high: { label: 'HIGH RISK', cls: 'risk-badge-high', barCls: 'bar-high' },
};

export default function ProjectRisksPanel({ data }) {
  const projects = data?.projects || [];

  if (projects.length === 0) {
    return (
      <div className="intel-empty-card">
        <p>No project risk assessments found for the selected scope.</p>
      </div>
    );
  }

  return (
    <div className="project-risks-panel">
      <div className="panel-intro-header">
        <div>
          <h3>Project Delivery Risk Assessments</h3>
          <p className="section-subtext">
            Risk scores (0–100) are deterministically calculated from completion rates, overdue tasks,
            and blocked items. Explanations and recommendations are AI-synthesized from verified project data.
          </p>
        </div>
      </div>

      <div className="project-cards-grid">
        {projects.map((proj) => {
          const levelKey = (proj.deterministic_risk_level || 'low').toLowerCase();
          const levelConfig = RISK_LEVEL_CONFIG[levelKey] || RISK_LEVEL_CONFIG.low;
          const score = typeof proj.deterministic_risk_score === 'number'
            ? Math.round(proj.deterministic_risk_score)
            : 0;

          return (
            <div key={proj.project_id} className="project-risk-card">
              <div className="card-top-bar">
                <div>
                  <h4 className="project-card-title">{proj.project_name}</h4>
                  <span className="project-id-sub">Project ID #{proj.project_id}</span>
                </div>
                <div className="risk-level-tag-wrap">
                  <span className={`risk-level-badge ${levelConfig.cls}`}>{levelConfig.label}</span>
                </div>
              </div>

              {/* Deterministic Score Progress Gauge */}
              <div className="score-gauge-wrap">
                <div className="score-labels">
                  <span className="score-title">Deterministic Risk Score</span>
                  <span className="score-value">{score} <span className="score-max">/ 100</span></span>
                </div>
                <div className="score-bar-track">
                  <div
                    className={`score-bar-fill ${levelConfig.barCls}`}
                    style={{ width: `${Math.min(Math.max(score, 5), 100)}%` }}
                    role="progressbar"
                    aria-valuenow={score}
                    aria-valuemin="0"
                    aria-valuemax="100"
                  />
                </div>
              </div>

              {/* Primary Risk Factors */}
              {proj.primary_risk_factors && proj.primary_risk_factors.length > 0 && (
                <div className="risk-factors-section">
                  <span className="factors-label">Contributing Risk Factors:</span>
                  <div className="factors-tags">
                    {proj.primary_risk_factors.map((factor, idx) => (
                      <span key={idx} className="factor-tag">
                        ⚠️ {factor}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Root Cause Explanation */}
              <div className="explanation-box">
                <span className="box-title">🔍 Delivery Trajectory & Evidence:</span>
                <p className="box-text">{proj.risk_explanation}</p>
              </div>

              {/* Potential Consequences */}
              {proj.potential_consequences && (
                <div className="consequences-box">
                  <span className="box-title">⚠️ Potential Consequences:</span>
                  <p className="box-text">{proj.potential_consequences}</p>
                </div>
              )}

              {/* Recommended Preventive Actions */}
              {proj.recommended_actions && proj.recommended_actions.length > 0 && (
                <div className="actions-box">
                  <span className="box-title">🛡️ Recommended Preventive Actions:</span>
                  <ul className="actions-list">
                    {proj.recommended_actions.map((act, idx) => (
                      <li key={idx}>{act}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="card-advisory-tag">
                <span>Advisory recommendation only. No automated changes applied to sprints or assignments.</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
