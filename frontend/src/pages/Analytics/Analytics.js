/**
 * pages/Analytics/Analytics.js
 *
 * Centralized Enterprise Analytics Dashboard.
 * Connects directly to backend /api/v1/analytics endpoints with Recharts
 * visualizations, role-based scoping (Admin, Manager, Team Lead),
 * and real operational performance metrics.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

import {
  getAnalyticsOverview,
  getProjectAnalytics,
  getWorkforceAnalytics,
  getOperationsAnalytics,
  getAnalyticsTrends,
} from '../../api/analyticsApi';
import LoadingSpinner from '../../components/common/LoadingSpinner';
import './Analytics.css';

// Chart Theme Colors (Lavender / Violet Enterprise Palette)
const COLORS = {
  primary: '#7c5cfc',
  primaryDark: '#6342e8',
  accent: '#a78bfa',
  indigo: '#6366f1',
  success: '#16a34a',
  warning: '#d97706',
  danger: '#dc2626',
  info: '#0891b2',
  muted: '#9b96b3',
  grid: '#f1effa',
};

const SEVERITY_COLORS = {
  low: '#16a34a',
  medium: '#0891b2',
  high: '#d97706',
  critical: '#dc2626',
};

const HEALTH_BADGES = {
  healthy: { label: 'Healthy', badgeClass: 'badge green' },
  at_risk: { label: 'At Risk', badgeClass: 'badge amber' },
  critical: { label: 'Critical', badgeClass: 'badge red' },
};

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

export default function Analytics() {
  const role = currentRole();
  const isExecutive = ['admin', 'manager'].includes(role);
  // Viewer: read-only, aggregate figures only. The backend refuses the
  // workforce endpoint (named employees' workloads), so it isn't loaded.
  const isViewer = role === 'viewer';
  const hasOrgView = isExecutive || isViewer;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('overview'); // 'overview', 'projects', 'workforce', 'operations'

  // Data states
  const [overview, setOverview] = useState(null);
  const [projectsData, setProjectsData] = useState([]);
  const [workforce, setWorkforce] = useState(null);
  const [operations, setOperations] = useState(null);
  const [trends, setTrends] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (hasOrgView) {
        // Fetch all datasets in parallel for the organization-wide view
        const [ov, proj, wf, ops, tr] = await Promise.all([
          getAnalyticsOverview().catch(() => null),
          getProjectAnalytics(selectedProjectId ? Number(selectedProjectId) : null).catch(() => ({ projects: [] })),
          isExecutive
            ? getWorkforceAnalytics(selectedProjectId ? Number(selectedProjectId) : null).catch(() => null)
            : Promise.resolve(null),
          getOperationsAnalytics().catch(() => null),
          getAnalyticsTrends(14, selectedProjectId ? Number(selectedProjectId) : null).catch(() => ({ daily_trends: [] })),
        ]);

        setOverview(ov);
        setProjectsData(proj?.projects || []);
        setWorkforce(wf);
        setOperations(ops);
        setTrends(tr?.daily_trends || []);
      } else {
        // Team Lead view: project-scoped analytics
        const [proj, wf, tr] = await Promise.all([
          getProjectAnalytics().catch(() => ({ projects: [] })),
          getWorkforceAnalytics().catch(() => null),
          getAnalyticsTrends(14).catch(() => ({ daily_trends: [] })),
        ]);
        setProjectsData(proj?.projects || []);
        setWorkforce(wf);
        setTrends(tr?.daily_trends || []);
      }
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to load enterprise analytics. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [hasOrgView, isExecutive, selectedProjectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="module-page analytics-page">
        <div className="module-page-header">
          <div className="module-page-icon purple" aria-hidden="true">📊</div>
          <div>
            <h1>Analytics Dashboard</h1>
            <p>Aggregating real enterprise performance metrics and operations...</p>
          </div>
        </div>
        <div className="content-panel">
          <LoadingSpinner label="Compiling live enterprise analytics..." />
        </div>
      </div>
    );
  }

  // Formatting chart trends
  const trendChartData = (trends || []).map((t) => ({
    date: t.date.slice(5), // 'MM-DD'
    'Tasks Completed': t.tasks_completed,
    'Tasks Created': t.tasks_created,
    'Tickets Created': t.tickets_created,
    'Tickets Resolved': t.tickets_resolved,
    'Incidents Reported': t.incidents_reported,
  }));

  // Incident severity donut data
  const incidentSevData = operations?.incidents?.severity_breakdown
    ? Object.entries(operations.incidents.severity_breakdown)
        .filter(([, count]) => count > 0)
        .map(([sev, count]) => ({
          name: sev.toUpperCase(),
          value: count,
          color: SEVERITY_COLORS[sev] || COLORS.primary,
        }))
    : [];

  return (
    <div className="module-page analytics-page">
      {/* Header */}
      <div className="module-page-header">
        <div className="module-page-icon purple" aria-hidden="true">📊</div>
        <div className="header-info-wrap">
          <div>
            <h1>Analytics Dashboard</h1>
            <p>
              Cross-module business intelligence, sprint velocity, and enterprise health metrics.
            </p>
          </div>

          {/* Project selector for Admins and Managers */}
          {isExecutive && projectsData.length > 0 && (
            <div className="project-filter-wrap">
              <label htmlFor="project-filter">Scope View:</label>
              <select
                id="project-filter"
                className="select-input"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
              >
                <option value="">Organization-Wide (All Projects)</option>
                {projectsData.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.project_name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="alert error analytics-error-bar">
          <span>{error}</span>
          <button className="btn-secondary" onClick={loadData}>Retry</button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="analytics-tabs-nav" role="tablist">
        <button
          className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
          role="tab"
          aria-selected={activeTab === 'overview'}
        >
          Executive Overview
        </button>
        <button
          className={`tab-btn ${activeTab === 'projects' ? 'active' : ''}`}
          onClick={() => setActiveTab('projects')}
          role="tab"
          aria-selected={activeTab === 'projects'}
        >
          Project Performance ({projectsData.length})
        </button>
        {!isViewer && (
          <button
            className={`tab-btn ${activeTab === 'workforce' ? 'active' : ''}`}
            onClick={() => setActiveTab('workforce')}
            role="tab"
            aria-selected={activeTab === 'workforce'}
          >
            Workforce & Workload
          </button>
        )}
        {hasOrgView && (
          <button
            className={`tab-btn ${activeTab === 'operations' ? 'active' : ''}`}
            onClick={() => setActiveTab('operations')}
            role="tab"
            aria-selected={activeTab === 'operations'}
          >
            Cross-Module Operations
          </button>
        )}
      </div>

      {/* TAB 1: EXECUTIVE OVERVIEW */}
      {activeTab === 'overview' && (
        <>
          {overview && (
            <div className="analytics-grid">
              <div className="kpi-card" style={{ '--kpi-color': COLORS.primary }}>
                <div className="kpi-label">Active Workforce</div>
                <div className="kpi-value">{overview.active_employees}</div>
                <div className="kpi-sub">{overview.total_employees} registered employees</div>
              </div>

              <div className="kpi-card" style={{ '--kpi-color': COLORS.indigo }}>
                <div className="kpi-label">Enterprise Projects</div>
                <div className="kpi-value">{overview.total_projects}</div>
                <div className="kpi-sub">{overview.active_projects} active project teams</div>
              </div>

              <div className="kpi-card" style={{ '--kpi-color': COLORS.success }}>
                <div className="kpi-label">Task Completion Rate</div>
                <div className="kpi-value">{overview.overall_task_completion_rate}%</div>
                <div className="kpi-sub">{overview.completed_tasks} / {overview.total_tasks} tasks done</div>
              </div>

              <div className="kpi-card" style={{ '--kpi-color': overview.open_incidents > 0 ? COLORS.danger : COLORS.success }}>
                <div className="kpi-label">Open Incidents</div>
                <div className="kpi-value">{overview.open_incidents}</div>
                <div className="kpi-sub">{overview.open_incidents > 0 ? 'Requires attention' : 'Systems healthy'}</div>
              </div>

              <div className="kpi-card" style={{ '--kpi-color': COLORS.info }}>
                <div className="kpi-label">Support Tickets</div>
                <div className="kpi-value">{overview.open_support_tickets}</div>
                <div className="kpi-sub">Active open / in-progress</div>
              </div>

              <div className="kpi-card" style={{ '--kpi-color': COLORS.accent }}>
                <div className="kpi-label">AI Action Items Converted</div>
                <div className="kpi-value">{overview.action_items_conversion_rate}%</div>
                <div className="kpi-sub">{overview.action_items_converted_count} / {overview.meeting_action_items_count} sprint tasks</div>
              </div>
            </div>
          )}

          {/* Time Series Activity Trends */}
          <div className="chart-panel">
            <div className="chart-header">
              <div>
                <h2>Enterprise Activity Trends (Past 14 Days)</h2>
                <p className="chart-sub">Daily volume of task creations, sprint completions, and incident intake.</p>
              </div>
            </div>
            {trendChartData.length > 0 ? (
              <div className="recharts-wrapper-custom" style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorDone" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.success} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={COLORS.success} stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorTasks" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
                    <XAxis dataKey="date" tick={{ fill: COLORS.muted, fontSize: 12 }} />
                    <YAxis tick={{ fill: COLORS.muted, fontSize: 12 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8, borderColor: '#e9e5f7' }} />
                    <Legend />
                    <Area type="monotone" dataKey="Tasks Completed" stroke={COLORS.success} fillOpacity={1} fill="url(#colorDone)" />
                    <Area type="monotone" dataKey="Tasks Created" stroke={COLORS.primary} fillOpacity={1} fill="url(#colorTasks)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="empty-chart-note">No activity trend data recorded in this period.</div>
            )}
          </div>
        </>
      )}

      {/* TAB 2: PROJECT PERFORMANCE */}
      {activeTab === 'projects' && (
        <div className="projects-analytics-section">
          {/* Stacked Task Status Bar Chart */}
          <div className="chart-panel">
            <div className="chart-header">
              <div>
                <h2>Project Task Distribution & Status</h2>
                <p className="chart-sub">Overview of completed, in-progress, todo, and blocked tasks per project team.</p>
              </div>
            </div>
            {projectsData.length > 0 ? (
              <div className="recharts-wrapper-custom" style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={projectsData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
                    <XAxis dataKey="project_name" tick={{ fill: COLORS.muted, fontSize: 12 }} />
                    <YAxis tick={{ fill: COLORS.muted, fontSize: 12 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8, borderColor: '#e9e5f7' }} />
                    <Legend />
                    <Bar dataKey="tasks_done" name="Done" stackId="a" fill={COLORS.success} />
                    <Bar dataKey="tasks_in_progress" name="In Progress" stackId="a" fill={COLORS.indigo} />
                    <Bar dataKey="tasks_todo" name="To Do" stackId="a" fill={COLORS.accent} />
                    <Bar dataKey="tasks_blocked" name="Blocked" stackId="a" fill={COLORS.danger} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="empty-chart-note">No project task data available.</div>
            )}
          </div>

          {/* Project Health Table */}
          <div className="content-panel">
            <h2>Project Performance Scorecard</h2>
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Project</th>
                    <th>Team Lead</th>
                    <th>Headcount</th>
                    <th>Active Sprint</th>
                    <th>Overdue Tasks</th>
                    <th>Completion</th>
                    <th>Health</th>
                  </tr>
                </thead>
                <tbody>
                  {projectsData.map((p) => {
                    const health = HEALTH_BADGES[p.health_status] || HEALTH_BADGES.healthy;
                    return (
                      <tr key={p.project_id}>
                        <td><strong>{p.project_name}</strong></td>
                        <td>{p.team_lead_name || '—'}</td>
                        <td>{p.member_count} members</td>
                        <td>{p.active_sprint_name || <span className="muted-note">No active sprint</span>}</td>
                        <td>
                          {p.tasks_overdue > 0 ? (
                            <span className="badge red">{p.tasks_overdue} overdue</span>
                          ) : (
                            <span className="badge green">0</span>
                          )}
                        </td>
                        <td>
                          <div className="completion-cell">
                            <span>{p.completion_rate}%</span>
                            <div className="mini-progress-bar">
                              <div
                                className="mini-progress-fill"
                                style={{ width: `${p.completion_rate}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={health.badgeClass}>{health.label}</span>
                        </td>
                      </tr>
                    );
                  })}
                  {projectsData.length === 0 && (
                    <tr>
                      <td colSpan={7} className="muted-note text-center">No projects match the selected scope.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: WORKFORCE & ALLOCATION */}
      {activeTab === 'workforce' && (
        <div className="workforce-analytics-section">
          {workforce?.attendance_summary && (
            <div className="attendance-strip">
              <div className="strip-item">
                <span className="strip-label">Average Check-in Rate</span>
                <span className="strip-value">{Math.round(workforce.attendance_summary.average_checkin_rate * 100)}%</span>
              </div>
              <div className="strip-item">
                <span className="strip-label">Present Records</span>
                <span className="strip-value text-green">{workforce.attendance_summary.present_count}</span>
              </div>
              <div className="strip-item">
                <span className="strip-label">Late Check-ins</span>
                <span className="strip-value text-amber">{workforce.attendance_summary.late_count}</span>
              </div>
              <div className="strip-item">
                <span className="strip-label">Approved Leave</span>
                <span className="strip-value text-purple">{workforce.attendance_summary.on_leave_count}</span>
              </div>
            </div>
          )}

          <div className="two-col-grid">
            {/* Department Headcount Bar */}
            <div className="chart-panel">
              <div className="chart-header">
                <h2>Headcount by Department</h2>
              </div>
              {workforce?.department_distribution?.length > 0 ? (
                <div className="recharts-wrapper-custom" style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={workforce.department_distribution}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 30, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
                      <XAxis type="number" tick={{ fill: COLORS.muted, fontSize: 12 }} />
                      <YAxis type="category" dataKey="department_name" tick={{ fill: COLORS.muted, fontSize: 12 }} />
                      <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8 }} />
                      <Bar dataKey="employee_count" name="Headcount" fill={COLORS.primary} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="empty-chart-note">No department distributions found.</div>
              )}
            </div>

            {/* Project Allocation Donut */}
            <div className="chart-panel">
              <div className="chart-header">
                <h2>Project Team Staffing</h2>
              </div>
              {workforce?.project_allocations?.length > 0 ? (
                <div className="recharts-wrapper-custom" style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={workforce.project_allocations}
                        dataKey="headcount"
                        nameKey="project_name"
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={80}
                        paddingAngle={4}
                      >
                        {workforce.project_allocations.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={[COLORS.primary, COLORS.indigo, COLORS.accent, COLORS.info][index % 4]}
                          />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8 }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="empty-chart-note">No project team allocations recorded.</div>
              )}
            </div>
          </div>

          {/* Individual Workload Summary (No punitive scoring) */}
          <div className="content-panel">
            <h2>Workforce Task Allocation</h2>
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Project</th>
                    <th>Tasks Assigned</th>
                    <th>Completed</th>
                    <th>In Progress / Pending</th>
                    <th>Overdue</th>
                  </tr>
                </thead>
                <tbody>
                  {workforce?.workload_distribution?.map((w) => (
                    <tr key={w.employee_id}>
                      <td><strong>{w.employee_name}</strong></td>
                      <td>{w.project_name || 'Unassigned'}</td>
                      <td>{w.tasks_assigned}</td>
                      <td><span className="badge green">{w.tasks_completed}</span></td>
                      <td>{w.tasks_pending}</td>
                      <td>
                        {w.tasks_overdue > 0 ? (
                          <span className="badge red">{w.tasks_overdue}</span>
                        ) : (
                          <span className="badge muted">0</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(!workforce?.workload_distribution || workforce.workload_distribution.length === 0) && (
                    <tr>
                      <td colSpan={6} className="muted-note text-center">No employee workload entries available.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: CROSS-MODULE OPERATIONS */}
      {activeTab === 'operations' && hasOrgView && operations && (
        <div className="operations-analytics-section">
          <div className="two-col-grid">
            {/* Incident Severity Breakdown */}
            <div className="chart-panel">
              <div className="chart-header">
                <h2>Incidents by Severity</h2>
                <p className="chart-sub">
                  Total: {operations.incidents.total} | Avg Resolution: {operations.incidents.avg_resolution_minutes ? `${operations.incidents.avg_resolution_minutes}m` : 'N/A'}
                </p>
              </div>
              {incidentSevData.length > 0 ? (
                <div className="recharts-wrapper-custom" style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={incidentSevData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={({ name, value }) => `${name}: ${value}`}
                      >
                        {incidentSevData.map((entry, index) => (
                          <Cell key={`sev-cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8 }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="empty-chart-note">No incidents recorded in the system. All services operational.</div>
              )}
            </div>

            {/* Customer Support Category Breakdown */}
            <div className="chart-panel">
              <div className="chart-header">
                <h2>Customer Support Tickets by Category</h2>
                <p className="chart-sub">Total Tickets: {operations.support.total_tickets} ({operations.support.open_tickets} Open)</p>
              </div>
              {operations.support?.category_distribution?.length > 0 ? (
                <div className="recharts-wrapper-custom" style={{ width: '100%', height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={operations.support.category_distribution}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 30, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
                      <XAxis type="number" tick={{ fill: COLORS.muted, fontSize: 12 }} />
                      <YAxis type="category" dataKey="category_name" tick={{ fill: COLORS.muted, fontSize: 12 }} />
                      <Tooltip contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8 }} />
                      <Bar dataKey="ticket_count" name="Tickets" fill={COLORS.info} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="empty-chart-note">No support tickets currently recorded.</div>
              )}
            </div>
          </div>

          {/* Recruitment & Meeting Intelligence Scorecards */}
          <div className="two-col-grid">
            <div className="content-panel">
              <h2>Recruitment AI Pipeline</h2>
              <div className="stat-row">
                <div className="stat-card">
                  <div className="stat-label">Active Job Postings</div>
                  <div className="stat-value">{operations.recruitment.open_positions}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Applications Received</div>
                  <div className="stat-value">{operations.recruitment.total_applications}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Shortlisted Candidates</div>
                  <div className="stat-value text-green">{operations.recruitment.shortlisted}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Waiting AI Screening</div>
                  <div className="stat-value text-amber">{operations.recruitment.waiting}</div>
                </div>
              </div>
            </div>

            <div className="content-panel">
              <h2>Meeting Intelligence Metrics</h2>
              <div className="stat-row">
                <div className="stat-card">
                  <div className="stat-label">Meetings Processed</div>
                  <div className="stat-value">{operations.meetings.total_meetings}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Total Duration (min)</div>
                  <div className="stat-value">{operations.meetings.total_duration_minutes}m</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">AI Action Items Extracted</div>
                  <div className="stat-value text-purple">{operations.meetings.action_items_total}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Sprint Conversion Rate</div>
                  <div className="stat-value text-green">{operations.meetings.conversion_rate}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
