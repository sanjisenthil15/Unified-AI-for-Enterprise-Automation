/**
 * pages/Attendance/Attendance.js
 *
 * Every employee: check in/out for today, see their own history, mark
 * planned leave. If they lead a project (or are admin/hr_manager), an
 * extra "My Team" tab shows the whole team's check-in rate.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  checkIn, checkOut, getMyAttendance, getTeamAttendance, markLeave,
} from '../../api/attendanceApi';
import { getMyEmployeeRecord, listProjects } from '../../api/employeeApi';
import { getLedProjects } from '../../utils/teamLead';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';

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

const RATE_BADGE = (rate) => (rate >= 0.9 ? 'green' : rate >= 0.7 ? 'amber' : 'red');

export default function Attendance() {
  const [myEmployee, setMyEmployee] = useState(null);
  const [notOnboarded, setNotOnboarded] = useState(false);
  const [myRecords, setMyRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const [showLeaveForm, setShowLeaveForm] = useState(false);
  const [leaveForm, setLeaveForm] = useState({ startDate: '', endDate: '', reason: '' });

  const [tab, setTab] = useState('me');
  const [allProjects, setAllProjects] = useState([]);
  const [ledProjects, setLedProjects] = useState([]);
  const [teamProjectId, setTeamProjectId] = useState('');
  const [teamData, setTeamData] = useState([]);

  const isOverride = ['admin', 'hr_manager'].includes(currentRole());

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
        const records = await getMyAttendance();
        setMyRecords(records);
      }
      setError('');
    } catch {
      setError('Could not load attendance data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const today = todayStr();
  const todayRecord = myRecords.find((r) => r.work_date === today);
  const canCheckIn = !todayRecord || !todayRecord.check_in_at;
  const canCheckOut = todayRecord && todayRecord.check_in_at && !todayRecord.check_out_at;

  async function handleCheckIn() {
    setBusy(true);
    try {
      await checkIn();
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not check in.');
    } finally {
      setBusy(false);
    }
  }

  async function handleCheckOut() {
    setBusy(true);
    try {
      await checkOut();
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not check out.');
    } finally {
      setBusy(false);
    }
  }

  async function handleMarkLeave(e) {
    e.preventDefault();
    if (!leaveForm.startDate || !leaveForm.endDate) return;
    try {
      await markLeave(leaveForm);
      setLeaveForm({ startDate: '', endDate: '', reason: '' });
      setShowLeaveForm(false);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not mark leave.');
    }
  }

  const teamSelectableProjects = isOverride ? allProjects : ledProjects;
  const canSeeTeamTab = teamSelectableProjects.length > 0;

  const loadTeam = useCallback(async (projectId) => {
    if (!projectId) { setTeamData([]); return; }
    try {
      const data = await getTeamAttendance({ projectId: Number(projectId) });
      setTeamData(data);
    } catch {
      setError('Could not load team attendance.');
    }
  }, []);

  useEffect(() => {
    if (tab === 'team' && teamProjectId) loadTeam(teamProjectId);
  }, [tab, teamProjectId, loadTeam]);

  if (loading) {
    return (
      <div className="module-page">
        <div className="module-page-header">
          <div className="module-page-icon blue" aria-hidden="true">🕒</div>
          <div><h1>Attendance</h1><p>Loading…</p></div>
        </div>
      </div>
    );
  }

  return (
    <div className="module-page">
      <div className="module-page-header">
        <div className="module-page-icon blue" aria-hidden="true">🕒</div>
        <div><h1>Attendance</h1><p>Check in and out, track your history, and plan leave.</p></div>
      </div>

      {error && <div className="alert error">{error}</div>}

      {notOnboarded ? (
        <div className="content-panel">
          <p style={{ color: 'var(--text-muted)' }}>No employee record yet — contact HR to be onboarded.</p>
        </div>
      ) : (
        <>
          {canSeeTeamTab && (
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
              <button className={tab === 'me' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('me')}>My Attendance</button>
              <button className={tab === 'team' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTab('team')}>My Team</button>
            </div>
          )}

          {tab === 'me' && (
            <>
              <div className="content-panel">
                <h2>Today</h2>
                <p style={{ color: 'var(--text-muted)' }}>
                  {todayRecord?.check_in_at
                    ? `Checked in at ${new Date(todayRecord.check_in_at).toLocaleTimeString()}`
                    : 'Not checked in yet today.'}
                  {todayRecord?.check_out_at && ` — checked out at ${new Date(todayRecord.check_out_at).toLocaleTimeString()}`}
                </p>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button className="btn-primary" onClick={handleCheckIn} disabled={busy || !canCheckIn}>Check In</button>
                  <button className="btn-secondary" onClick={handleCheckOut} disabled={busy || !canCheckOut}>Check Out</button>
                  <button className="btn-secondary" onClick={() => setShowLeaveForm((v) => !v)}>
                    {showLeaveForm ? 'Close' : 'Mark leave'}
                  </button>
                </div>

                {showLeaveForm && (
                  <form onSubmit={handleMarkLeave} style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                    <div className="field-group">
                      <label>Start date</label>
                      <input className="field-input" type="date" value={leaveForm.startDate}
                        onChange={(e) => setLeaveForm((f) => ({ ...f, startDate: e.target.value }))} required />
                    </div>
                    <div className="field-group">
                      <label>End date</label>
                      <input className="field-input" type="date" value={leaveForm.endDate}
                        onChange={(e) => setLeaveForm((f) => ({ ...f, endDate: e.target.value }))} required />
                    </div>
                    <div className="field-group">
                      <label>Reason</label>
                      <input className="field-input" value={leaveForm.reason}
                        onChange={(e) => setLeaveForm((f) => ({ ...f, reason: e.target.value }))} />
                    </div>
                    <button type="submit" className="btn-primary">Submit</button>
                  </form>
                )}
              </div>

              <div className="content-panel">
                <h2>History</h2>
                {myRecords.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)' }}>No attendance recorded yet.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                        <th style={{ padding: '0.5rem' }}>Date</th>
                        <th style={{ padding: '0.5rem' }}>Check in</th>
                        <th style={{ padding: '0.5rem' }}>Check out</th>
                        <th style={{ padding: '0.5rem' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {myRecords.map((r) => (
                        <tr key={r.id} style={{ borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <td style={{ padding: '0.5rem' }}>{r.work_date}</td>
                          <td style={{ padding: '0.5rem' }}>{r.check_in_at ? new Date(r.check_in_at).toLocaleTimeString() : '—'}</td>
                          <td style={{ padding: '0.5rem' }}>{r.check_out_at ? new Date(r.check_out_at).toLocaleTimeString() : '—'}</td>
                          <td style={{ padding: '0.5rem' }}><span className="badge blue">{r.status.replace('_', ' ')}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}

          {tab === 'team' && (
            <div className="content-panel">
              <h2>Team attendance</h2>
              <div className="field-group" style={{ maxWidth: 320, marginBottom: '1rem' }}>
                <label>Project</label>
                <select className="field-select" value={teamProjectId} onChange={(e) => setTeamProjectId(e.target.value)}>
                  <option value="">Select a project…</option>
                  {teamSelectableProjects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>

              {teamProjectId && (
                teamData.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)' }}>No team members yet.</p>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                        <th style={{ padding: '0.5rem' }}>Employee</th>
                        <th style={{ padding: '0.5rem' }}>Job title</th>
                        <th style={{ padding: '0.5rem' }}>Check-in rate (30d)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {teamData.map((entry) => (
                        <tr key={entry.employee.id} style={{ borderBottom: '1px solid var(--border, #e2e8f0)' }}>
                          <td style={{ padding: '0.5rem' }}>{entry.employee.full_name}</td>
                          <td style={{ padding: '0.5rem' }}>{entry.employee.job_title}</td>
                          <td style={{ padding: '0.5rem' }}>
                            <span className={`badge ${RATE_BADGE(entry.checkin_rate)}`}>
                              {Math.round(entry.checkin_rate * 100)}%
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
