/**
 * pages/Dashboard/Dashboard.js
 *
 * Role-aware landing page — built entirely from endpoints that already
 * exist and are already authorized for each role, no new backend work:
 *   - admin/hr_manager: enterprise project overview + recruitment stats
 *   - team lead (derived via utils/teamLead, same as Sprints.js/Chat.js):
 *     their led project(s)' progress + flagged teammates
 *   - everyone: their own ongoing tasks, this week's team progress, and
 *     recent unread activity (covers "if anyone messaged me" — mentions
 *     and chat notifications already flow through the same feed)
 * Quick-link module cards stay below as secondary navigation.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getEnterpriseOverview, getManagerReview, getMyTasks, listSprints, listTasks } from '../../api/sprintsApi';
import { getRecruitmentStats } from '../../api/recruitmentApi';
import { getMyEmployeeRecord, listProjects } from '../../api/employeeApi';
import { getMyNotifications } from '../../api/notificationsApi';
import { getLedProjects } from '../../utils/teamLead';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import '../Sprints/Sprints.css';
import './Dashboard.css';

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function currentRole() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.role?.name?.toLowerCase() ?? '';
  } catch {
    return '';
  }
}

const TASK_STATUS_BADGE = { todo: 'purple', in_progress: 'blue', blocked: 'red', done: 'green' };

const MODULES = [
  {
    id: 'recruitment', icon: '🤖', title: 'AI Recruitment',
    description: 'Automate resume screening, rank candidates by fit score, and schedule interviews with AI-driven insights.',
    colorClass: 'card-recruitment', status: 'Active', to: '/hr',
  },
  {
    id: 'support', icon: '🎧', title: 'Customer Support',
    description: 'AI-powered ticket management with automatic replies, priority triage, and real-time escalation detection.',
    colorClass: 'card-support', status: 'Active', to: '/customer-support',
  },
  {
    id: 'incident', icon: '🚨', title: 'Incident Management',
    description: 'Log, triage, and resolve incidents faster. AI suggests severity levels and assigns the right team automatically.',
    colorClass: 'card-incident', status: 'Active', to: '/incidents',
  },
  {
    id: 'meeting', icon: '🎙️', title: 'Meeting Intelligence',
    description: 'Upload audio recordings. Get Whisper transcriptions, Gemini summaries, and action-item extraction instantly.',
    colorClass: 'card-meeting', status: 'Active', to: '/meetings',
  },
  {
    id: 'employee', icon: '👥', title: 'Employee Management',
    description: 'Manage employee profiles, departments, and roles. AI-generated performance insights keep HR proactive.',
    colorClass: 'card-employee', status: 'Active', to: '/employees',
  },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const role = currentRole();
  const isOverride = ['admin', 'hr_manager'].includes(role);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Admin / HR
  const [overview, setOverview] = useState([]);
  const [recruitmentStats, setRecruitmentStats] = useState(null);

  // Team lead
  const [ledReviews, setLedReviews] = useState([]); // [{ project, entries }]

  // Everyone else
  const [myTasks, setMyTasks] = useState([]);
  const [sprintProgress, setSprintProgress] = useState(null); // { name, done, total }
  const [recentActivity, setRecentActivity] = useState([]);
  const [notOnboarded, setNotOnboarded] = useState(false);

  const load = useCallback(async () => {
    setError('');
    try {
      if (isOverride) {
        const [ov, stats] = await Promise.all([
          getEnterpriseOverview().catch(() => []),
          getRecruitmentStats().catch(() => null),
        ]);
        setOverview(ov);
        setRecruitmentStats(stats);
        setLoading(false);
        return;
      }

      // These four are all independent of each other — fire together
      // instead of awaiting one at a time, since this page loads on
      // every single login.
      const [me, tasks, activity, projects] = await Promise.all([
        getMyEmployeeRecord().catch((err) => {
          if (err.response?.status === 404) { setNotOnboarded(true); return null; }
          throw err;
        }),
        getMyTasks().catch(() => []),
        getMyNotifications({ unreadOnly: true }).catch(() => []),
        listProjects().catch(() => []),
      ]);
      setMyTasks(tasks);
      setRecentActivity(activity.slice(0, 6));

      if (me) {
        const led = getLedProjects(me.id, projects);
        const ledReviewsPromise = led.length > 0
          ? Promise.all(led.map(async (p) => {
              const entries = await getManagerReview({ projectId: p.id }).catch(() => []);
              return { project: p, entries };
            }))
          : Promise.resolve([]);

        const sprintProgressPromise = me.project
          ? listSprints(me.project.id).catch(() => []).then(async (sprints) => {
              const today = todayStr();
              const current = sprints.find((s) => s.start_date <= today && today <= s.end_date);
              if (!current) return null;
              const sprintTasks = await listTasks(current.id).catch(() => []);
              const done = sprintTasks.filter((t) => t.status === 'done').length;
              return { name: current.name, done, total: sprintTasks.length };
            })
          : Promise.resolve(null);

        const [reviews, progress] = await Promise.all([ledReviewsPromise, sprintProgressPromise]);
        if (led.length > 0) setLedReviews(reviews);
        if (progress) setSprintProgress(progress);
      }
    } catch {
      setError('Could not load your dashboard.');
    } finally {
      setLoading(false);
    }
  }, [isOverride]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="module-page">
        <div className="module-page-header">
          <div className="module-page-icon blue" aria-hidden="true">🏠</div>
          <div><h1>Dashboard</h1><p>Loading…</p></div>
        </div>
      </div>
    );
  }

  return (
    <div className="module-page" style={{ maxWidth: 1200 }}>
      <div className="module-page-header">
        <div className="module-page-icon blue" aria-hidden="true">🏠</div>
        <div><h1>Dashboard</h1><p>Your work, at a glance.</p></div>
      </div>

      {error && (
        <div className="alert error" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{error}</span>
          <button className="btn-secondary" onClick={() => { setLoading(true); load(); }}>Try again</button>
        </div>
      )}

      {isOverride ? (
        <>
          <div className="content-panel">
            <h2>Enterprise Overview</h2>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Team lead</th>
                  <th>Completion</th>
                  <th>Flagged</th>
                </tr>
              </thead>
              <tbody>
                {overview.map((p) => (
                  <tr key={p.project_id} className="clickable-row" onClick={() => navigate(`/sprints`)}>
                    <td><strong>{p.project_name}</strong></td>
                    <td>{p.team_lead?.full_name || '—'}</td>
                    <td>
                      <div className="task-progress-bar" style={{ width: 100 }}>
                        <div className="task-progress-fill" style={{ width: `${Math.round(p.completion_rate * 100)}%` }} />
                      </div>
                    </td>
                    <td>
                      {p.flagged_count > 0
                        ? <span className="badge red">{p.flagged_count}</span>
                        : <span className="badge green">0</span>}
                    </td>
                  </tr>
                ))}
                {overview.length === 0 && (
                  <tr><td colSpan={4} className="muted-note">No projects yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {recruitmentStats && (
            <div className="content-panel">
              <h2>Recruitment</h2>
              <div className="stat-row">
                <div className="stat-card">
                  <div className="stat-label">Open Positions</div>
                  <div className="stat-value">{recruitmentStats.open_positions}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Applications</div>
                  <div className="stat-value">{recruitmentStats.applications}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Shortlisted</div>
                  <div className="stat-value">{recruitmentStats.shortlisted}</div>
                </div>
              </div>
            </div>
          )}
        </>
      ) : notOnboarded ? (
        <div className="content-panel"><p className="muted-note">No employee record yet — contact HR to be onboarded.</p></div>
      ) : (
        <>
          {ledReviews.length > 0 && (
            <div className="content-panel">
              <h2>Team Progress</h2>
              {ledReviews.map(({ project, entries }) => {
                const totalTasks = entries.reduce((s, e) => s + e.tasks_total, 0);
                const doneTasks = entries.reduce((s, e) => s + e.tasks_done, 0);
                const rate = totalTasks ? doneTasks / totalTasks : 0;
                const flagged = entries.filter((e) => e.flagged);
                return (
                  <div key={project.id} style={{ marginBottom: '1rem' }}>
                    <div className="panel-header-row">
                      <strong>{project.name}</strong>
                      <button className="btn-secondary" onClick={() => navigate('/sprints')}>View sprints</button>
                    </div>
                    <div className="task-progress-bar"><div className="task-progress-fill" style={{ width: `${Math.round(rate * 100)}%` }} /></div>
                    <p className="muted-note" style={{ marginTop: '0.4rem' }}>{doneTasks} / {totalTasks} tasks complete</p>
                    {flagged.length > 0 && (
                      <p style={{ marginTop: '0.4rem' }}>
                        <span className="badge red">Needs attention</span>{' '}
                        {flagged.map((e) => e.employee.full_name).join(', ')}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="content-panel">
            <div className="panel-header-row">
              <h2>My Work</h2>
              <button className="btn-secondary" onClick={() => navigate('/sprints')}>View all</button>
            </div>
            {sprintProgress && (
              <div style={{ marginBottom: '1rem' }}>
                <p className="muted-note">This week's team progress — {sprintProgress.name}</p>
                <div className="task-progress-bar"><div className="task-progress-fill" style={{ width: `${sprintProgress.total ? Math.round((sprintProgress.done / sprintProgress.total) * 100) : 0}%` }} /></div>
                <p className="muted-note" style={{ marginTop: '0.4rem' }}>{sprintProgress.done} / {sprintProgress.total} tasks complete</p>
              </div>
            )}
            {myTasks.length === 0 ? (
              <p className="muted-note">No ongoing work assigned right now.</p>
            ) : (
              <table className="data-table">
                <thead><tr><th>Task</th><th>Status</th><th>Due</th></tr></thead>
                <tbody>
                  {myTasks.slice(0, 6).map((t) => (
                    <tr key={t.id}>
                      <td>{t.title}</td>
                      <td><span className={`badge ${TASK_STATUS_BADGE[t.status] || 'purple'}`}>{t.status.replace('_', ' ')}</span></td>
                      <td>{t.due_date || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="content-panel">
            <div className="panel-header-row">
              <h2>Recent Activity</h2>
              <button className="btn-secondary" onClick={() => navigate('/notifications')}>View all</button>
            </div>
            {recentActivity.length === 0 ? (
              <p className="muted-note">Nothing new — you're all caught up.</p>
            ) : (
              <div>
                {recentActivity.map((n) => (
                  <div key={n.id} className="notification-row unread"
                    onClick={() => n.link && navigate(n.link)}>
                    {n.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <div className="content-panel">
        <h2>Quick Links</h2>
        <div className="modules-grid" role="list" aria-label="Enterprise module cards">
          {MODULES.map((mod) => (
            <article
              key={mod.id}
              className={`module-card ${mod.colorClass}`}
              role="listitem"
              tabIndex={0}
              aria-label={`${mod.title} module`}
              onClick={() => navigate(mod.to)}
              onKeyDown={(e) => e.key === 'Enter' && navigate(mod.to)}
              style={{ cursor: 'pointer' }}
            >
              <div className="card-icon-wrap" aria-hidden="true">{mod.icon}</div>
              <div className="card-body">
                <h2 className="card-title">{mod.title}</h2>
                <p className="card-description">{mod.description}</p>
              </div>
              <div className="card-footer">
                <span className="card-status active">{mod.status}</span>
                <span className="card-arrow" aria-hidden="true">→</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}
