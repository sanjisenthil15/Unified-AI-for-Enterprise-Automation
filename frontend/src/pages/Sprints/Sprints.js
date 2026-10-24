/**
 * pages/Sprints/Sprints.js
 *
 * Every employee: see their project's sprints and a Kanban board of
 * tasks, update their own assigned tasks. If they lead the selected
 * project (or are admin/hr_manager), they additionally get sprint/task
 * creation, a burndown chart, and the "Team Review" tab.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  createSprint, createTask, generateWeeklySprints, getBurndown, getEnterpriseOverview,
  getManagerReview, listSprints, listTasks, updateTask,
} from '../../api/sprintsApi';
import { getMyEmployeeRecord, listProjects } from '../../api/employeeApi';
import { getTeamAttendance } from '../../api/attendanceApi';
import { getLedProjects } from '../../utils/teamLead';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './Sprints.css';

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function currentRole() {
  try {
    const user = JSON.parse(localStorage.getItem('user'));
    return user?.role?.name?.toLowerCase() ?? '';
  } catch {
    return '';
  }
}

const TASK_COLUMNS = [
  { key: 'todo', label: 'To do' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'blocked', label: 'Blocked' },
  { key: 'done', label: 'Done' },
];

export default function Sprints() {
  const navigate = useNavigate();
  const isOverride = ['admin', 'hr_manager'].includes(currentRole());

  const [myEmployee, setMyEmployee] = useState(null);
  const [notOnboarded, setNotOnboarded] = useState(false);
  const [allProjects, setAllProjects] = useState([]);
  const [ledProjects, setLedProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [projectId, setProjectId] = useState('');
  const [sprints, setSprints] = useState([]);
  const [sprintId, setSprintId] = useState('');
  const [tasks, setTasks] = useState([]);
  const [members, setMembers] = useState([]);
  const [burndown, setBurndown] = useState([]);
  const [tab, setTab] = useState('board');
  const [manageTaskId, setManageTaskId] = useState(null);
  const [review, setReview] = useState([]);
  const [overview, setOverview] = useState([]);
  const [generating, setGenerating] = useState(false);

  const [showSprintForm, setShowSprintForm] = useState(false);
  const [sprintForm, setSprintForm] = useState({ name: '', startDate: '', endDate: '' });
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [taskForm, setTaskForm] = useState({ title: '', assigneeId: '', dueDate: '' });

  const selectableProjects = isOverride ? allProjects : (myEmployee?.project ? [myEmployee.project, ...ledProjects] : ledProjects);
  const uniqueSelectableProjects = Array.from(new Map(selectableProjects.map((p) => [p.id, p])).values());
  const isManager = isOverride || ledProjects.some((p) => p.id === Number(projectId));

  const load = useCallback(async () => {
    try {
      const [me, projects] = await Promise.all([
        getMyEmployeeRecord().catch((err) => {
          if (err.response?.status === 404) { setNotOnboarded(true); return null; }
          throw err;
        }),
        listProjects(),
      ]);
      setAllProjects(projects);
      if (me) {
        setMyEmployee(me);
        setLedProjects(getLedProjects(me.id, projects));
        setProjectId((cur) => cur || (me.project?.id ?? projects[0]?.id ?? ''));
      } else if (projects.length) {
        setProjectId((cur) => cur || projects[0].id);
      }
      setError('');
    } catch {
      setError('Could not load sprint data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadSprints = useCallback(async (pid) => {
    if (!pid) { setSprints([]); return; }
    try {
      const data = await listSprints(Number(pid));
      setSprints(data);
      setSprintId((cur) => {
        if (data.some((s) => s.id === Number(cur))) return cur;
        // listSprints is newest-first, so data[0] is the furthest-out
        // (often still-empty) sprint — default to the one covering
        // today instead, so a freshly-opened project lands somewhere
        // with actual content, not a blank future week.
        const today = todayStr();
        const current = data.find((s) => s.start_date <= today && today <= s.end_date);
        return current?.id ?? data[0]?.id ?? '';
      });
    } catch {
      setError('Could not load sprints for this project.');
    }
  }, []);

  useEffect(() => { loadSprints(projectId); }, [projectId, loadSprints]);

  useEffect(() => {
    if (!projectId || !isManager) { setMembers([]); return; }
    getTeamAttendance({ projectId: Number(projectId) })
      .then((entries) => setMembers(entries.map((e) => e.employee)))
      .catch(() => {});
  }, [projectId, isManager]);

  const loadTasks = useCallback(async (sid) => {
    if (!sid) { setTasks([]); setBurndown([]); return; }
    try {
      const [taskList, burndownData] = await Promise.all([listTasks(Number(sid)), getBurndown(Number(sid))]);
      setTasks(taskList);
      setBurndown(burndownData);
    } catch {
      setError('Could not load this sprint.');
    }
  }, []);

  useEffect(() => { loadTasks(sprintId); }, [sprintId, loadTasks]);

  useEffect(() => {
    if (tab === 'review' && projectId && isManager) {
      getManagerReview({ projectId: Number(projectId) }).then(setReview).catch(() => setError('Could not load team review.'));
    }
  }, [tab, projectId, isManager]);

  useEffect(() => {
    if (tab === 'overview' && isOverride) {
      getEnterpriseOverview().then(setOverview).catch(() => setError('Could not load the enterprise overview.'));
    }
  }, [tab, isOverride]);

  async function handleCreateSprint(e) {
    e.preventDefault();
    try {
      const sprint = await createSprint({ projectId: Number(projectId), ...sprintForm });
      setSprintForm({ name: '', startDate: '', endDate: '' });
      setShowSprintForm(false);
      await loadSprints(projectId);
      setSprintId(sprint.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create sprint.');
    }
  }

  async function handleGenerateWeekly() {
    setGenerating(true);
    setError('');
    try {
      await generateWeeklySprints(Number(projectId));
      await loadSprints(projectId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not generate weekly sprints.');
    } finally {
      setGenerating(false);
    }
  }

  async function handleCreateTask(e) {
    e.preventDefault();
    if (!sprintId) return;
    try {
      await createTask(Number(sprintId), taskForm);
      setTaskForm({ title: '', assigneeId: '', dueDate: '' });
      setShowTaskForm(false);
      loadTasks(sprintId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create task.');
    }
  }

  async function handleTaskStatus(taskId, status) {
    try {
      await updateTask(taskId, { status });
      loadTasks(sprintId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not update task.');
    }
  }

  async function handleToggleDone(task) {
    try {
      if (task.status === 'done') {
        await updateTask(task.id, { status: 'todo', progressPercent: 0 });
      } else {
        await updateTask(task.id, { status: 'done' });
      }
      loadTasks(sprintId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not update task.');
    }
  }

  async function handleReassign(taskId, assigneeId) {
    try {
      await updateTask(taskId, { assigneeId: assigneeId ? Number(assigneeId) : null });
      loadTasks(sprintId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not reassign task.');
    }
  }

  async function handleDueDateChange(taskId, dueDate) {
    try {
      await updateTask(taskId, { dueDate: dueDate || null });
      loadTasks(sprintId);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not update due date.');
    }
  }

  function handleExtendTwoDays(task) {
    const base = task.due_date ? new Date(task.due_date) : new Date();
    base.setDate(base.getDate() + 2);
    handleDueDateChange(task.id, base.toISOString().slice(0, 10));
  }

  const selectedSprint = sprints.find((s) => s.id === Number(sprintId));
  const maxBurndown = Math.max(1, ...burndown.map((b) => b.total));
  const selectedProject = uniqueSelectableProjects.find((p) => p.id === Number(projectId));

  if (loading) {
    return (
      <div className="module-page">
        <div className="module-page-header">
          <div className="module-page-icon cyan" aria-hidden="true">🏃</div>
          <div><h1>Sprints</h1><p>Loading…</p></div>
        </div>
      </div>
    );
  }

  return (
    <div className="module-page">
      <div className="module-page-header">
        <div className="module-page-icon cyan" aria-hidden="true">🏃</div>
        <div><h1>Sprints</h1><p>Weekly sprints, task assignments, and team progress.</p></div>
      </div>

      {error && (
        <div className="alert error" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{error}</span>
          <button className="btn-secondary" onClick={() => { setLoading(true); load(); }}>Try again</button>
        </div>
      )}

      {notOnboarded && !allProjects.length ? (
        <div className="content-panel"><p className="muted-note">No employee record yet — contact HR to be onboarded.</p></div>
      ) : (
        <>
          <div className="content-panel">
            <div className="field-row">
              <div className="field-group field-group-wide">
                <label>Project</label>
                <select className="field-select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">Select a project…</option>
                  {uniqueSelectableProjects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="field-group field-group-wide">
                <label>Sprint</label>
                <select className="field-select" value={sprintId} onChange={(e) => setSprintId(e.target.value)}>
                  <option value="">Select a sprint…</option>
                  {[...sprints].sort((a, b) => a.start_date.localeCompare(b.start_date)).map((s) => (
                    <option key={s.id} value={s.id}>{s.name} ({s.status})</option>
                  ))}
                </select>
              </div>
              {isManager && projectId && (
                <button className="btn-secondary" onClick={() => setShowSprintForm((v) => !v)}>
                  {showSprintForm ? 'Close' : '+ New sprint'}
                </button>
              )}
              {isManager && projectId && selectedProject?.deadline && (
                <button className="btn-secondary" onClick={handleGenerateWeekly} disabled={generating}
                  title={`Fills weekly sprint shells up to ${selectedProject.deadline}`}>
                  {generating ? 'Generating…' : '📅 Generate weekly sprints'}
                </button>
              )}
              {isOverride && (
                <button className={tab === 'overview' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('overview')}>
                  🏢 Enterprise Overview
                </button>
              )}
            </div>

            {showSprintForm && (
              <form onSubmit={handleCreateSprint} className="field-row" style={{ marginTop: '1rem' }}>
                <div className="field-group">
                  <label>Name</label>
                  <input className="field-input" value={sprintForm.name}
                    onChange={(e) => setSprintForm((f) => ({ ...f, name: e.target.value }))} required />
                </div>
                <div className="field-group">
                  <label>Start date</label>
                  <input className="field-input" type="date" value={sprintForm.startDate}
                    onChange={(e) => setSprintForm((f) => ({ ...f, startDate: e.target.value }))} required />
                </div>
                <div className="field-group">
                  <label>End date</label>
                  <input className="field-input" type="date" value={sprintForm.endDate}
                    onChange={(e) => setSprintForm((f) => ({ ...f, endDate: e.target.value }))} required />
                </div>
                <button type="submit" className="btn-primary">Create</button>
              </form>
            )}
          </div>

          {sprintId && (
            <>
              {isManager && (
                <div className="tab-bar">
                  <button className={tab === 'board' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('board')}>Board</button>
                  <button className={tab === 'review' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('review')}>Team Review</button>
                </div>
              )}

              {tab === 'board' && (
                <div className="content-panel">
                  <div className="panel-header-row">
                    <h2>{selectedSprint?.name}</h2>
                    {isManager && (
                      <button className="btn-primary" onClick={() => setShowTaskForm((v) => !v)}>
                        {showTaskForm ? 'Close' : '+ New task'}
                      </button>
                    )}
                  </div>

                  {showTaskForm && (
                    <form onSubmit={handleCreateTask} className="field-row" style={{ marginTop: '1rem' }}>
                      <div className="field-group">
                        <label>Title</label>
                        <input className="field-input" value={taskForm.title}
                          onChange={(e) => setTaskForm((f) => ({ ...f, title: e.target.value }))} required />
                      </div>
                      <div className="field-group">
                        <label>Assignee</label>
                        <select className="field-select" value={taskForm.assigneeId}
                          onChange={(e) => setTaskForm((f) => ({ ...f, assigneeId: e.target.value }))}>
                          <option value="">Unassigned</option>
                          {members.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                        </select>
                      </div>
                      <div className="field-group">
                        <label>Due date</label>
                        <input className="field-input" type="date" value={taskForm.dueDate}
                          onChange={(e) => setTaskForm((f) => ({ ...f, dueDate: e.target.value }))} />
                      </div>
                      <button type="submit" className="btn-primary">Add task</button>
                    </form>
                  )}

                  {selectedSprint?.status === 'active' && burndown.length > 0 && (
                    <>
                      <h3 className="section-subheading">Burndown</h3>
                      <div className="burndown-chart">
                        {burndown.map((b) => (
                          <div className="burndown-bar-wrap" key={b.date}>
                            <div className="burndown-bar" style={{ height: `${(b.remaining / maxBurndown) * 100}%` }} />
                            <span className="burndown-bar-label">{b.date.slice(5)}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}

                  {tasks.length === 0 ? (
                    <div className="kanban-empty-state">
                      <p>No tasks in this sprint yet.</p>
                      {isManager && (
                        <button className="btn-secondary" onClick={() => setShowTaskForm(true)}>+ New task</button>
                      )}
                    </div>
                  ) : (
                  <div className="kanban-board">
                    {TASK_COLUMNS.map((col) => (
                      <div className="kanban-column" key={col.key}>
                        <div className="kanban-column-title">{col.label} ({tasks.filter((t) => t.status === col.key).length})</div>
                        {tasks.filter((t) => t.status === col.key).map((task) => {
                          const isMine = myEmployee && task.assignee?.id === myEmployee.id;
                          const isOverdue = task.due_date && task.status !== 'done' && task.due_date < todayStr();
                          const managing = manageTaskId === task.id;
                          return (
                            <div className="kanban-card" key={task.id}>
                              <div className="kanban-card-title">{task.title}</div>
                              <div className="kanban-card-meta">
                                {task.assignee?.full_name || 'Unassigned'}
                                {task.due_date && (
                                  <span className={isOverdue ? 'kanban-overdue' : ''}> · due {task.due_date}</span>
                                )}
                              </div>
                              <div className="task-progress-bar">
                                <div className="task-progress-fill" style={{ width: `${task.progress_percent}%` }} />
                              </div>

                              {isMine && !isManager && (
                                <button
                                  className={`kanban-card-action ${task.status === 'done' ? 'btn-secondary' : 'btn-primary'}`}
                                  onClick={() => handleToggleDone(task)}
                                >
                                  {task.status === 'done' ? '↺ Reopen' : '✓ Mark Done'}
                                </button>
                              )}

                              {isManager && (
                                <>
                                  <button
                                    className="kanban-manage-toggle btn-secondary"
                                    onClick={() => setManageTaskId(managing ? null : task.id)}
                                  >
                                    {managing ? 'Close' : 'Manage'}
                                  </button>
                                  {managing && (
                                    <div className="kanban-manage-panel">
                                      <select className="field-select" value={task.status}
                                        onChange={(e) => handleTaskStatus(task.id, e.target.value)}>
                                        {TASK_COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                                      </select>
                                      <select className="field-select" value={task.assignee?.id || ''}
                                        onChange={(e) => handleReassign(task.id, e.target.value)}>
                                        <option value="">Unassigned</option>
                                        {members.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                                      </select>
                                      <div className="kanban-manage-due-row">
                                        <input type="date" className="field-input" value={task.due_date || ''}
                                          onChange={(e) => handleDueDateChange(task.id, e.target.value)} />
                                        <button className="btn-secondary"
                                          onClick={() => handleExtendTwoDays(task)}>
                                          +2 days
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                  )}
                </div>
              )}

              {tab === 'review' && isManager && (
                <div className="content-panel">
                  <h2>Team Review (last 7 days)</h2>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Employee</th>
                        <th>Check-in rate</th>
                        <th>Tasks done</th>
                        <th>Overdue</th>
                        <th>Status</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {review.map((r) => (
                        <tr key={r.employee.id} className={r.flagged ? 'review-row-flagged' : ''}>
                          <td>{r.employee.full_name}</td>
                          <td>{Math.round(r.checkin_rate * 100)}%</td>
                          <td>{r.tasks_done} / {r.tasks_total}</td>
                          <td>{r.tasks_overdue_incomplete}</td>
                          <td>
                            {r.flagged
                              ? <span className="badge red">Needs attention</span>
                              : <span className="badge green">On track</span>}
                          </td>
                          <td>
                            <button className="btn-secondary" onClick={() => navigate(`/chat?with=${r.employee.user_id}`)}>
                              Message
                            </button>
                          </td>
                        </tr>
                      ))}
                      {review.length === 0 && (
                        <tr><td colSpan={6} className="muted-note">No team members yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          {tab === 'overview' && isOverride && (
            <div className="content-panel">
              <h2>Every project, at a glance</h2>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Project</th>
                    <th>Team lead</th>
                    <th>Deadline</th>
                    <th>Active sprint</th>
                    <th>Completion</th>
                    <th>Flagged</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.map((p) => (
                    <tr key={p.project_id} className="clickable-row"
                      onClick={() => { setProjectId(String(p.project_id)); setTab('board'); }}>
                      <td><strong>{p.project_name}</strong></td>
                      <td>{p.team_lead?.full_name || '—'}</td>
                      <td>{p.deadline || '—'}</td>
                      <td>{p.active_sprint?.name || '—'}</td>
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
                    <tr><td colSpan={6} className="muted-note">No projects yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
