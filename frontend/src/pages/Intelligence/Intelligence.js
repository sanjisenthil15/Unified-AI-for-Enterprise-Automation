/**
 * pages/Intelligence/Intelligence.js
 *
 * Enterprise AI Intelligence Dashboard.
 * Integrates directly with /api/v1/intelligence endpoints:
 *   - Executive Intelligence Summary (Admin & Manager)
 *   - Project Delivery Risks (Admin, Manager, Team Leader)
 *   - Sprint Delay Trajectories (Admin, Manager, Team Leader)
 *   - Workload Bottlenecks (Admin, Manager, Team Leader)
 *   - Cross-Module Operations Intelligence (Admin & Manager)
 *   - Cache Refresh with 10s Cooldown Handling (HTTP 429)
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  getExecutiveSummary,
  getProjectRisks,
  getSprintDelays,
  getWorkloadBottlenecks,
  getOperationsInsights,
  refreshIntelligence,
} from '../../api/intelligenceApi';
import { getMyEmployeeRecord, listProjects } from '../../api/employeeApi';
import { getLedProjects } from '../../utils/teamLead';
import LoadingSpinner from '../../components/common/LoadingSpinner';

import ExecutiveSummaryPanel from './components/ExecutiveSummaryPanel';
import ProjectRisksPanel from './components/ProjectRisksPanel';
import SprintDelaysPanel from './components/SprintDelaysPanel';
import WorkloadBottlenecksPanel from './components/WorkloadBottlenecksPanel';
import OperationsInsightsPanel from './components/OperationsInsightsPanel';

import './Intelligence.css';

function currentUser() {
  try {
    return JSON.parse(localStorage.getItem('user')) || null;
  } catch {
    return null;
  }
}

function currentRole() {
  const user = currentUser();
  return user?.role?.name?.toLowerCase() || '';
}

export default function Intelligence() {
  const navigate = useNavigate();
  const role = currentRole();
  const authDisabled = process.env.REACT_APP_AUTH_DISABLED === 'true';
  const isExecutive = authDisabled || ['admin', 'manager'].includes(role);

  // Authorization & Project scoping states
  const [initLoading, setInitLoading] = useState(true);
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [allProjects, setAllProjects] = useState([]);
  const [assignedProject, setAssignedProject] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState('');

  // Active Tab state: Executive defaults to 'executive', Team Leader to 'risks'
  const [activeTab, setActiveTab] = useState(isExecutive ? 'executive' : 'risks');

  // Intelligence Data States
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [executiveData, setExecutiveData] = useState(null);
  const [projectRisksData, setProjectRisksData] = useState(null);
  const [sprintDelaysData, setSprintDelaysData] = useState(null);
  const [workloadData, setWorkloadData] = useState(null);
  const [operationsData, setOperationsData] = useState(null);

  // Refresh & Cooldown states
  const [refreshing, setRefreshing] = useState(false);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);

  // Step 1: Initial role & leadership resolution
  useEffect(() => {
    let isMounted = true;

    async function checkAuthorization() {
      try {
        const projects = await listProjects().catch(() => []);
        if (!isMounted) return;
        setAllProjects(projects);

        if (isExecutive) {
          setIsAuthorized(true);
          setInitLoading(false);
          return;
        }

        // For non-executive roles (e.g. employee): verify if they lead any project
        const me = await getMyEmployeeRecord().catch(() => null);
        if (!isMounted) return;

        if (me) {
          const led = getLedProjects(me.id, projects);
          if (led.length > 0) {
            setIsAuthorized(true);
            setAssignedProject(led[0]);
            setSelectedProjectId(String(led[0].id));
            setActiveTab('risks');
          } else {
            setIsAuthorized(false);
          }
        } else {
          setIsAuthorized(false);
        }
      } catch (err) {
        if (isMounted) setIsAuthorized(false);
      } finally {
        if (isMounted) setInitLoading(false);
      }
    }

    checkAuthorization();
    return () => { isMounted = false; };
  }, [isExecutive]);

  // Step 2: Load data for the active tab and selected project
  const loadActiveTabData = useCallback(async () => {
    if (!isAuthorized) return;

    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      const pId = selectedProjectId ? Number(selectedProjectId) : (assignedProject?.id || null);

      if (activeTab === 'executive' && isExecutive) {
        const data = await getExecutiveSummary();
        setExecutiveData(data);
      } else if (activeTab === 'risks') {
        const data = await getProjectRisks(pId);
        setProjectRisksData(data);
      } else if (activeTab === 'sprints') {
        const data = await getSprintDelays(pId);
        setSprintDelaysData(data);
      } else if (activeTab === 'workload') {
        const data = await getWorkloadBottlenecks(pId);
        setWorkloadData(data);
      } else if (activeTab === 'operations' && isExecutive) {
        const data = await getOperationsInsights();
        setOperationsData(data);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 403) {
        setError('Access denied: You are not authorized to view intelligence for this scope.');
      } else {
        setError(typeof detail === 'string' ? detail : 'Failed to load enterprise intelligence.');
      }
    } finally {
      setLoading(false);
    }
  }, [isAuthorized, isExecutive, activeTab, selectedProjectId, assignedProject]);

  useEffect(() => {
    if (!initLoading && isAuthorized) {
      loadActiveTabData();
    }
  }, [initLoading, isAuthorized, loadActiveTabData]);

  // Cooldown countdown timer effect
  useEffect(() => {
    if (cooldownRemaining <= 0) return;

    const timer = setInterval(() => {
      setCooldownRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [cooldownRemaining]);

  // Step 3: Refresh Handler with Cooldown
  async function handleRefresh() {
    if (refreshing || cooldownRemaining > 0) return;

    setRefreshing(true);
    setError('');
    setSuccessMsg('');

    const pId = selectedProjectId ? Number(selectedProjectId) : (assignedProject?.id || null);

    try {
      const res = await refreshIntelligence({
        scope: isExecutive && !pId ? 'org' : 'project',
        projectId: pId,
      });

      setSuccessMsg(res?.message || 'Intelligence cache successfully refreshed.');
      // Reload current tab's live data
      await loadActiveTabData();
    } catch (err) {
      if (err?.response?.status === 429) {
        const detail = err.response.data?.detail || '';
        // Extract seconds if present in message or Retry-After header
        const retryHeader = err.response.headers?.['retry-after'];
        let waitSec = retryHeader ? parseInt(retryHeader, 10) : 10;

        const match = detail.match(/(\d+)\s*seconds/i);
        if (match) waitSec = parseInt(match[1], 10);

        setCooldownRemaining(waitSec);
        setError(`Refresh cooldown active. Please wait ${waitSec}s before refreshing again.`);
      } else {
        const detail = err?.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Failed to refresh intelligence cache.');
      }
    } finally {
      setRefreshing(false);
    }
  }

  // Loading initial role authorization
  if (initLoading) {
    return (
      <div className="module-page intelligence-page">
        <div className="module-page-header">
          <div className="module-page-icon purple" aria-hidden="true">🧠</div>
          <div>
            <h1>AI Enterprise Intelligence</h1>
            <p>Authorizing operational intelligence scope...</p>
          </div>
        </div>
        <div className="intel-empty-card">
          <LoadingSpinner label="Validating permissions and project scopes..." />
        </div>
      </div>
    );
  }

  // Unauthorized Access Barrier (Regular employees who are not Team Leads)
  if (!isAuthorized) {
    return (
      <div className="module-page intelligence-page">
        <div className="access-denied-panel">
          <div className="access-denied-icon" aria-hidden="true">🔒</div>
          <h2>Access Restricted</h2>
          <p>
            You do not have permission to view enterprise intelligence.
            Only Administrators, Managers, and assigned Team Leaders have access to operational AI insights.
          </p>
          <button
            type="button"
            className="access-denied-btn"
            onClick={() => navigate('/dashboard')}
          >
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="module-page intelligence-page">
      {/* Header with Project Selector and Refresh Action */}
      <div className="module-page-header">
        <div className="module-page-icon purple" aria-hidden="true">🧠</div>
        <div className="header-info-wrap">
          <div>
            <h1>AI Enterprise Intelligence</h1>
            <p>Predictive delivery risks, workload bottlenecks, and explainable recommendations.</p>
          </div>

          <div className="intel-header-controls">
            {/* Project Scope Filter */}
            {isExecutive ? (
              <div className="intel-project-scope">
                <label htmlFor="intel-project-select">Project Scope:</label>
                <select
                  id="intel-project-select"
                  className="select-input"
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                >
                  <option value="">All Projects (Org-wide)</option>
                  {allProjects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="intel-project-scope">
                <label>Assigned Project:</label>
                <span className="assigned-project-badge">
                  {assignedProject?.name || `Project #${selectedProjectId}`}
                </span>
              </div>
            )}

            {/* Refresh Action */}
            <button
              type="button"
              className="intel-refresh-btn"
              onClick={handleRefresh}
              disabled={refreshing || cooldownRemaining > 0}
              title={cooldownRemaining > 0 ? `Cooldown active (${cooldownRemaining}s)` : 'Refresh intelligence cache'}
            >
              <span className={`refresh-icon ${refreshing ? 'refresh-spin' : ''}`} aria-hidden="true">⚡</span>
              {refreshing
                ? 'Analyzing...'
                : cooldownRemaining > 0
                ? `Cooldown (${cooldownRemaining}s)`
                : 'Refresh AI Insights'}
            </button>
          </div>
        </div>
      </div>

      {/* Advisory Banner */}
      <div className="intel-advisory-banner">
        <span className="advisory-icon" aria-hidden="true">ℹ️</span>
        <div>
          <strong>Enterprise AI Intelligence is strictly advisory:</strong> Explanations and recommendations
          require human review and authorization. No automated changes are applied to projects, tasks, or business operations.
        </div>
      </div>

      {/* Cooldown Alert Banner */}
      {cooldownRemaining > 0 && (
        <div className="intel-cooldown-bar" role="alert">
          <span>⏳ <strong>Rate Limiter Active:</strong> Please wait {cooldownRemaining} second{cooldownRemaining === 1 ? '' : 's'} before triggering another cache refresh.</span>
        </div>
      )}

      {/* Success Banner */}
      {successMsg && (
        <div className="intel-alert-bar success" role="status">
          <span>✅ {successMsg}</span>
          <button type="button" onClick={() => setSuccessMsg('')}>Dismiss</button>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="intel-alert-bar error" role="alert">
          <span>⚠️ {error}</span>
          <button type="button" onClick={() => setError('')}>Dismiss</button>
        </div>
      )}

      {/* Tabs Navigation */}
      <nav className="intel-tabs-nav" aria-label="Intelligence Sections">
        {isExecutive && (
          <button
            type="button"
            className={`intel-tab-btn ${activeTab === 'executive' ? 'active' : ''}`}
            onClick={() => setActiveTab('executive')}
          >
            <span aria-hidden="true">👑</span> Executive Summary
          </button>
        )}

        <button
          type="button"
          className={`intel-tab-btn ${activeTab === 'risks' ? 'active' : ''}`}
          onClick={() => setActiveTab('risks')}
        >
          <span aria-hidden="true">🎯</span> Project Risks
        </button>

        <button
          type="button"
          className={`intel-tab-btn ${activeTab === 'sprints' ? 'active' : ''}`}
          onClick={() => setActiveTab('sprints')}
        >
          <span aria-hidden="true">🏃</span> Sprint Delays
        </button>

        <button
          type="button"
          className={`intel-tab-btn ${activeTab === 'workload' ? 'active' : ''}`}
          onClick={() => setActiveTab('workload')}
        >
          <span aria-hidden="true">⚖️</span> Workload Bottlenecks
        </button>

        {isExecutive && (
          <button
            type="button"
            className={`intel-tab-btn ${activeTab === 'operations' ? 'active' : ''}`}
            onClick={() => setActiveTab('operations')}
          >
            <span aria-hidden="true">🛠️</span> Operations Insights
          </button>
        )}
      </nav>

      {/* Content Area */}
      {loading ? (
        <div className="intel-empty-card">
          <LoadingSpinner label="Analyzing enterprise metrics and synthesizing AI insights..." />
        </div>
      ) : (
        <div className="intel-tab-content">
          {activeTab === 'executive' && isExecutive && (
            <ExecutiveSummaryPanel data={executiveData} />
          )}

          {activeTab === 'risks' && (
            <ProjectRisksPanel data={projectRisksData} />
          )}

          {activeTab === 'sprints' && (
            <SprintDelaysPanel data={sprintDelaysData} />
          )}

          {activeTab === 'workload' && (
            <WorkloadBottlenecksPanel data={workloadData} />
          )}

          {activeTab === 'operations' && isExecutive && (
            <OperationsInsightsPanel data={operationsData} />
          )}
        </div>
      )}
    </div>
  );
}
