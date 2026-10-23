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
  createSprint, createTask, getBurndown, getManagerReview, listSprints, listTasks, updateTask,
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
      setSprintId((cur) => (data.some((s) => s.id === Number(cur)) ? cur : (data[0]?.id ?? '')));
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

      {error && <div className="alert error">{error}</div>}

      {notOnboarded && !allProjects.length ? (
        <div className="content-panel"><p style={{ color: 'var(--text-muted)' }}>No employee record yet — contact HR to be onboarded.</p></div>
      ) : (
        <>
          <div className="content-panel">
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div className="field-group" style={{ minWidth: 220 }}>
                <label>Project</label>
                <select className="field-select" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">Select a project…</option>
                  {uniqueSelectableProjects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="field-group" style={{ minWidth: 220 }}>
                <label>Sprint</label>
                <select className="field-select" value={sprintId} onChange={(e) => setSprintId(e.target.value)}>
                  <option value="">Select a sprint…</option>
                  {sprints.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.status})</option>)}
                </select>
              </div>
              {isManager && projectId && (
                <button className="btn-secondary" onClick={() => setShowSprintForm((v) => !v)}>
                  {showSprintForm ? 'Close' : '+ New sprint'}
                </button>
              )}
            </div>

            {showSprintForm && (
              <form onSubmit={handleCreateSprint} style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
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
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
                  <button className={tab === 'board' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('board')}>Board</button>
                  <button className={tab === 'review' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('review')}>Team Review</button>
                </div>
              )}

              {tab === 'board' && (
                <div className="content-panel">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h2 style={{ margin: 0 }}>{selectedSprint?.name}</h2>
                    {isManager && (
                      <button className="btn-primary" onClick={() => setShowTaskForm((v) => !v)}>
                        {showTaskForm ? 'Close' : '+ New task'}
                      </button>
                    )}
                  </div>

                  {showTaskForm && (
                    <form onSubmit={handleCreateTask} style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
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
                      <h3 style={{ fontSize: '0.9rem', marginTop: '1.5rem' }}>Burndown</h3>
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
                                  className={task.status === 'done' ? 'btn-secondary' : 'btn-primary'}
                                  style={{ marginTop: '0.5rem', width: '100%' }}
                                  onClick={() => handleToggleDone(task)}
                                >
                                  {task.status === 'done' ? '↺ Reopen' : '✓ Mark Done'}
                                </button>
                              )}

                              {isManager && (
                                <>
                                  <button
                                    className="btn-secondary"
                                    style={{ marginTop: '0.5rem', width: '100%', fontSize: '0.78rem' }}
                                    onClick={() => setManageTaskId(managing ? null : task.id)}
                                  >
                                    {managing ? 'Close' : 'Manage'}
                                  </button>
                                  {managing && (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
                                      <select className="field-select" value={task.status}
                                        onChange={(e) => handleTaskStatus(task.id, e.target.value)}
                                        style={{ fontSize: '0.78rem', padding: '0.3rem' }}>
                                        {TASK_COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                                      </select>
                                      <select className="field-select" value={task.assignee?.id || ''}
                                        onChange={(e) => handleReassign(task.id, e.target.value)}
                                        style={{ fontSize: '0.78rem', padding: '0.3rem' }}>
                                        <option value="">Unassigned</option>
                                        {members.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
                                      </select>
                                      <div style={{ display: 'flex', gap: '0.3rem' }}>
                                        <input type="date" className="field-input" value={task.due_date || ''}
                                          onChange={(e) => handleDueDateChange(task.id, e.target.value)}
                                          style={{ fontSize: '0.78rem', padding: '0.3rem', flex: 1 }} />
                                        <button className="btn-secondary" style={{ fontSize: '0.72rem', padding: '0.3rem 0.5rem' }}
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
                </div>
              )}

              {tab === 'review' && isManager && (
                <div className="content-panel">
                  <h2>Team Review (last 7 days)</h2>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                        <th style={{ padding: '0.5rem' }}>Employee</th>
                        <th style={{ padding: '0.5rem' }}>Check-in rate</th>
                        <th style={{ padding: '0.5rem' }}>Tasks done</th>
                        <th style={{ padding: '0.5rem' }}>Overdue</th>
                        <th style={{ padding: '0.5rem' }}>Status</th>
                        <th style={{ padding: '0.5rem' }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {review.map((r) => (
                        <tr key={r.employee.id} className={r.flagged ? 'review-row-flagged' : ''}
                          style={{ borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <td style={{ padding: '0.5rem' }}>{r.employee.full_name}</td>
                          <td style={{ padding: '0.5rem' }}>{Math.round(r.checkin_rate * 100)}%</td>
                          <td style={{ padding: '0.5rem' }}>{r.tasks_done} / {r.tasks_total}</td>
                          <td style={{ padding: '0.5rem' }}>{r.tasks_overdue_incomplete}</td>
                          <td style={{ padding: '0.5rem' }}>
                            {r.flagged
                              ? <span className="badge red">Needs attention</span>
                              : <span className="badge green">On track</span>}
                          </td>
                          <td style={{ padding: '0.5rem' }}>
                            <button className="btn-secondary" onClick={() => navigate(`/chat?with=${r.employee.user_id}`)}>
                              Message
                            </button>
                          </td>
                        </tr>
                      ))}
                      {review.length === 0 && (
                        <tr><td colSpan={6} style={{ padding: '0.5rem', color: 'var(--text-muted)' }}>No team members yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
