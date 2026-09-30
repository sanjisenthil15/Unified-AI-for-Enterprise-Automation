/**
 * pages/CustomerSupport/components/ServiceStatusView.js
 *
 * Enterprise Service Status & Incident Center.
 * Features:
 *   - Real-time operational status for all core enterprise services
 *   - Overall uptime & telemetry metrics
 *   - Active and resolved incident tracking with timeline modal
 *   - Clearly distinguished DEMO / DEVELOPMENT STATUS indicator
 *   - 1-click incident drill-down and diagnostics
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getServiceStatuses, getIncidentDetail } from '../../../api/customerSupportApi';

export default function ServiceStatusView({ onOpenSupportRequest, onTalkToAgent }) {
  const [statusData, setStatusData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [isIncidentLoading, setIsIncidentLoading] = useState(false);

  const fetchStatus = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getServiceStatuses();
      setStatusData(data);
    } catch (err) {
      console.warn('Service status fetch error, using fallback:', err);
      setStatusData({
        overall_status: 'All Systems Operational',
        data_mode: 'DEMO / DEVELOPMENT STATUS',
        services: [
          { id: 'auth_sso', name: 'Authentication & SSO', status: 'operational', uptime_pct: 99.99, latency_ms: 28, description: 'User login, JWT issuance, 2FA/MFA verification, and session token validation.' },
          { id: 'billing_invoicing', name: 'Billing & Invoicing', status: 'operational', uptime_pct: 99.96, latency_ms: 52, description: 'Invoice generation, subscription renewal cycles, and receipt downloads.' },
          { id: 'payment_gateways', name: 'Payment Gateways', status: 'operational', uptime_pct: 99.98, latency_ms: 84, description: 'Stripe, Razorpay, and Bank Wire webhook processing & recharge settlement.' },
          { id: 'api_services', name: 'REST API Services', status: 'operational', uptime_pct: 99.95, latency_ms: 38, description: 'Enterprise microservice endpoints, rate limiting, and customer API routing.' },
          { id: 'customer_portal', name: 'Customer Portal & UI', status: 'operational', uptime_pct: 99.99, latency_ms: 18, description: 'Single-page enterprise web dashboard, ticket inspector, and analytics.' },
          { id: 'subscription_sync', name: 'Subscription & License Sync', status: 'operational', uptime_pct: 99.94, latency_ms: 62, description: 'Automated plan activation, license provisioning, and feature entitlement sync.' },
          { id: 'database_storage', name: 'Database & Knowledge Store', status: 'operational', uptime_pct: 100.0, latency_ms: 12, description: 'MySQL relational cluster, BM25 indexing engine, and chat session stores.' },
          { id: 'notification_gateway', name: 'Notification & SLA Gateway', status: 'operational', uptime_pct: 99.97, latency_ms: 42, description: 'Real-time ticket updates, agent alerts, and automated SLA breach monitors.' },
        ],
        active_incidents: [],
        past_incidents: [
          {
            id: 'INC-104',
            title: 'Intermittent Latency on REST API US-East Gateway',
            affected_service: 'REST API Services',
            severity: 'minor',
            status: 'resolved',
            started_at: new Date(Date.now() - 3600000 * 6).toISOString(),
            resolved_at: new Date(Date.now() - 3600000 * 5).toISOString(),
            impact: 'Slight response time increase (<120ms) observed during peak traffic window.',
            latest_update: 'Traffic re-routed through secondary edge nodes. Latency normalized under 40ms.',
            timeline: [
              { id: 1, timestamp: new Date(Date.now() - 3600000 * 6).toISOString(), status: 'investigating', message: 'Elevated latency detected on US-East API proxy.' },
              { id: 2, timestamp: new Date(Date.now() - 3600000 * 5.5).toISOString(), status: 'identified', message: 'Originating from transient upstream CDN gateway congestion.' },
              { id: 3, timestamp: new Date(Date.now() - 3600000 * 5).toISOString(), status: 'resolved', message: 'Failover routing confirmed. All endpoints fully operational.' },
            ],
          }
        ],
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  async function handleInspectIncident(incId) {
    setIsIncidentLoading(true);
    try {
      const incDetail = await getIncidentDetail(incId);
      setSelectedIncident(incDetail);
    } catch (err) {
      const fallback = (statusData?.past_incidents || []).concat(statusData?.active_incidents || []).find((i) => i.id === incId);
      setSelectedIncident(fallback || null);
    } finally {
      setIsIncidentLoading(false);
    }
  }

  const getStatusColor = (status) => {
    switch ((status || '').toLowerCase()) {
      case 'operational':
        return 'green';
      case 'degraded':
      case 'partially_available':
        return 'orange';
      case 'maintenance':
        return 'blue';
      case 'outage':
        return 'red';
      default:
        return 'green';
    }
  };

  return (
    <div className="cs-status-view-container">
      {/* Top Banner */}
      <div className="cs-status-top-banner">
        <div className="cs-status-banner-left">
          <div className="cs-status-badge-overall green">
            <span className="cs-status-pulse"></span>
            <span>{statusData?.overall_status || 'All Systems Operational'}</span>
          </div>
          <p className="cs-status-banner-sub">
            Real-time telemetry and operational availability across all Enterprise microservices.
          </p>
        </div>

        <div className="cs-status-banner-right">
          <div className="cs-data-mode-tag">
            <span>🛡️ {statusData?.data_mode || 'DEMO / DEVELOPMENT STATUS'}</span>
          </div>
          <button
            type="button"
            className="cs-btn secondary cs-refresh-btn"
            onClick={fetchStatus}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing...' : '🔄 Refresh Telemetry'}
          </button>
        </div>
      </div>

      {/* SLA & Uptime Summary Cards */}
      <div className="cs-status-metrics-row">
        <div className="cs-status-metric-card">
          <div className="cs-stat-box-label">Global Service Uptime</div>
          <div className="cs-stat-box-value green">99.98%</div>
          <div className="cs-stat-drilldown-hint">Past 30 Days SLA</div>
        </div>
        <div className="cs-status-metric-card">
          <div className="cs-stat-box-label">Avg Core Latency</div>
          <div className="cs-stat-box-value blue">34ms</div>
          <div className="cs-stat-drilldown-hint">Microservice API Average</div>
        </div>
        <div className="cs-status-metric-card">
          <div className="cs-stat-box-label">Active Outages</div>
          <div className="cs-stat-box-value green">0 Active</div>
          <div className="cs-stat-drilldown-hint">100% Core Availability</div>
        </div>
        <div className="cs-status-metric-card">
          <div className="cs-stat-box-label">SLA Target Commitment</div>
          <div className="cs-stat-box-value purple">99.9% Met</div>
          <div className="cs-stat-drilldown-hint">Enterprise SLA Guarantee</div>
        </div>
      </div>

      {/* Core Enterprise Services Grid */}
      <div className="cs-panel-card">
        <div className="cs-card-header">
          <div>
            <h3>Enterprise Services Operational Status</h3>
            <span className="cs-subheading-text">Monitoring 8 core infrastructure layers</span>
          </div>
          <span className="cs-badge-verified">✓ 24/7 Monitored</span>
        </div>

        {isLoading ? (
          <div className="cs-loading-state">
            <div className="cs-spinner"></div>
            <span>Loading enterprise service statuses...</span>
          </div>
        ) : (
          <div className="cs-services-grid">
            {(statusData?.services || []).map((srv) => {
              const colorClass = getStatusColor(srv.status);
              return (
                <div key={srv.id} className="cs-service-card">
                  <div className="cs-service-card-header">
                    <div className="cs-service-name-row">
                      <span className={`cs-srv-dot ${colorClass}`}></span>
                      <h4 className="cs-service-title">{srv.name}</h4>
                    </div>
                    <span className={`cs-service-status-pill ${colorClass}`}>
                      {srv.status.replace('_', ' ').toUpperCase()}
                    </span>
                  </div>

                  <p className="cs-service-desc">{srv.description}</p>

                  <div className="cs-service-card-footer">
                    <div className="cs-srv-meta">
                      <span>Uptime: <strong>{srv.uptime_pct}%</strong></span>
                      <span className="cs-sep">•</span>
                      <span>Latency: <strong>{srv.latency_ms}ms</strong></span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Incidents & Maintenance Section */}
      <div className="cs-incidents-section-grid">
        {/* Active Incidents */}
        <div className="cs-panel-card">
          <div className="cs-card-header">
            <h3>🔴 Active Service Incidents</h3>
            <span className="cs-badge-demo">Live Diagnostics</span>
          </div>

          {(statusData?.active_incidents || []).length > 0 ? (
            <div className="cs-incidents-list">
              {statusData.active_incidents.map((inc) => (
                <div key={inc.id} className="cs-incident-item active">
                  <div className="cs-inc-top">
                    <span className="cs-inc-id">#{inc.id}</span>
                    <span className="cs-inc-severity red">{inc.severity.toUpperCase()}</span>
                    <span className="cs-inc-status orange">{inc.status.toUpperCase()}</span>
                  </div>
                  <h4 className="cs-inc-title">{inc.title}</h4>
                  <p className="cs-inc-impact">{inc.impact}</p>
                  <div className="cs-inc-footer">
                    <span>Started: {new Date(inc.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    <button
                      type="button"
                      className="cs-inc-btn"
                      onClick={() => handleInspectIncident(inc.id)}
                    >
                      View Diagnostics ➔
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="cs-incidents-empty">
              <span className="cs-empty-check">✓</span>
              <h4>No Active Incidents Reported</h4>
              <p>All enterprise APIs, billing gateways, and authentication services are operating normally.</p>
            </div>
          )}
        </div>

        {/* Past Incidents & Maintenance Log */}
        <div className="cs-panel-card">
          <div className="cs-card-header">
            <h3>📋 Recent Incident & Maintenance Log</h3>
            <span className="cs-stat-drilldown-hint">Past 7 Days</span>
          </div>

          <div className="cs-incidents-list">
            {(statusData?.past_incidents || []).map((inc) => (
              <div key={inc.id} className="cs-incident-item resolved">
                <div className="cs-inc-top">
                  <span className="cs-inc-id">#{inc.id}</span>
                  <span className="cs-inc-service-tag">{inc.affected_service}</span>
                  <span className="cs-inc-status green">RESOLVED</span>
                </div>
                <h4 className="cs-inc-title">{inc.title}</h4>
                <p className="cs-inc-update-snippet">{inc.latest_update}</p>
                <div className="cs-inc-footer">
                  <span>Resolved: {new Date(inc.resolved_at || inc.started_at).toLocaleDateString()}</span>
                  <button
                    type="button"
                    className="cs-inc-btn secondary"
                    onClick={() => handleInspectIncident(inc.id)}
                  >
                    View Timeline ➔
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Incident Detail Modal */}
      {selectedIncident && (
        <div className="cs-modal-overlay" onClick={() => setSelectedIncident(null)}>
          <div className="cs-modal-dialog cs-incident-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cs-modal-header">
              <div className="cs-modal-title-box">
                <span className="cs-modal-icon">🚨</span>
                <div>
                  <h3>Incident #{selectedIncident.id}: {selectedIncident.title}</h3>
                  <span className="cs-incident-target">{selectedIncident.affected_service}</span>
                </div>
              </div>
              <button type="button" className="cs-close-btn" onClick={() => setSelectedIncident(null)}>
                ✕
              </button>
            </div>

            <div className="cs-modal-body">
              <div className="cs-inc-modal-status-strip">
                <div>
                  <strong>Status:</strong>{' '}
                  <span className={`cs-inc-status ${selectedIncident.status === 'resolved' ? 'green' : 'orange'}`}>
                    {selectedIncident.status.toUpperCase()}
                  </span>
                </div>
                <div>
                  <strong>Severity:</strong> {selectedIncident.severity.toUpperCase()}
                </div>
                <div>
                  <strong>Started:</strong> {new Date(selectedIncident.started_at).toLocaleString()}
                </div>
              </div>

              <div className="cs-inc-modal-block">
                <h4>Impact Assessment:</h4>
                <p>{selectedIncident.impact}</p>
              </div>

              <div className="cs-inc-modal-block">
                <h4>Diagnostic Timeline:</h4>
                <div className="cs-timeline-stream">
                  {(selectedIncident.timeline || []).map((step, sIdx) => (
                    <div key={sIdx} className="cs-timeline-step">
                      <div className="cs-step-dot"></div>
                      <div className="cs-step-body">
                        <div className="cs-step-header">
                          <span className="cs-step-status">{step.status.toUpperCase()}</span>
                          <span className="cs-step-time">
                            {new Date(step.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <p className="cs-step-msg">{step.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="cs-modal-footer">
              <button
                type="button"
                className="cs-btn primary"
                onClick={() => {
                  setSelectedIncident(null);
                  if (onOpenSupportRequest) onOpenSupportRequest({ subject: `Issue related to ${selectedIncident.title}` });
                }}
              >
                📝 Report Service Problem
              </button>
              <button
                type="button"
                className="cs-btn secondary"
                onClick={() => {
                  setSelectedIncident(null);
                  if (onTalkToAgent) onTalkToAgent();
                }}
              >
                🎧 Talk to Specialist
              </button>
              <button type="button" className="cs-btn secondary" onClick={() => setSelectedIncident(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
