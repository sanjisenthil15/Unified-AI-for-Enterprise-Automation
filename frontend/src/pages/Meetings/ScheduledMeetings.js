/**
 * pages/Meetings/ScheduledMeetings.js
 *
 * Book a future meeting for a project team (team lead / admin / hr_manager)
 * and see meetings you organized or were invited to. Starting one launches
 * the same Online Meeting live session, linked back to this booking so it
 * fills in with a transcript/analysis/action items when it ends instead of
 * staying an empty "scheduled" placeholder.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listScheduledMeetings, scheduleMeeting } from '../../api/meetingApi';
import { startOnlineMeeting } from '../../api/onlineMeetingApi';
import { getMyEmployeeRecord, listProjects } from '../../api/employeeApi';
import { getLedProjects } from '../../utils/teamLead';
import '../Recruitment/Recruitment.css';
import './Meetings.css';

function currentRole() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.role?.name?.toLowerCase() ?? '';
  } catch {
    return '';
  }
}

function currentUserId() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.id ?? null;
  } catch {
    return null;
  }
}

function formatWhen(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

export default function ScheduledMeetings() {
  const navigate = useNavigate();
  const role = currentRole();
  const isOverride = ['admin', 'hr_manager'].includes(role);
  const myUserId = currentUserId();

  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(null);

  const [schedulableProjects, setSchedulableProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', projectId: '', scheduledAt: '' });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const load = useCallback(async () => {
    try {
      setMeetings(await listScheduledMeetings());
      setError('');
    } catch {
      setError('Could not load scheduled meetings.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const projects = await listProjects();
        if (isOverride) {
          setSchedulableProjects(projects);
          return;
        }
        const me = await getMyEmployeeRecord().catch(() => null);
        if (me) setSchedulableProjects(getLedProjects(me.id, projects));
      } catch {
        // No project to schedule for — the form just won't offer one.
      }
    })();
  }, [isOverride]);

  async function handleSchedule(event) {
    event.preventDefault();
    if (!form.title.trim() || !form.projectId || !form.scheduledAt) {
      setFormError('Title, project and date/time are all required.');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      await scheduleMeeting({
        title: form.title.trim(),
        description: form.description.trim() || undefined,
        projectId: Number(form.projectId),
        scheduledAt: new Date(form.scheduledAt).toISOString(),
      });
      setForm({ title: '', description: '', projectId: '', scheduledAt: '' });
      setShowForm(false);
      await load();
    } catch (err) {
      setFormError(err.response?.data?.detail || 'Could not schedule this meeting.');
    } finally {
      setSaving(false);
    }
  }

  async function handleStart(meeting) {
    setStarting(meeting.id);
    setError('');
    try {
      const session = await startOnlineMeeting(meeting.title, crypto.randomUUID(), { meetingId: meeting.id });
      navigate(`/meetings/online?session=${session.id}`);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail?.meeting_id) {
        navigate(`/meetings/online?session=${detail.meeting_id}`);
      } else {
        setError(typeof detail === 'string' ? detail : 'Could not start this meeting.');
      }
    } finally {
      setStarting(null);
    }
  }

  return (
    <div className="module-page mi-page">
      <div className="module-page-header">
        <div className="module-page-icon cyan" aria-hidden="true">📅</div>
        <div><h1>Scheduled Meetings</h1><p>Upcoming meetings you organized or were invited to.</p></div>
      </div>

      <div className="mi-list-toolbar">
        <Link className="mi-btn mi-btn-ghost" to="/meetings">← Meeting types</Link>
        {schedulableProjects.length > 0 && (
          <button className="mi-btn mi-btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Close' : '+ Schedule a meeting'}
          </button>
        )}
      </div>

      {showForm && (
        <div className="content-panel mi-panel">
          <h2>Schedule a meeting</h2>
          <p className="mi-muted">Every current member of the project you pick is invited and notified.</p>
          <form onSubmit={handleSchedule} className="mi-upload-grid">
            <label className="mi-field mi-field-wide">
              <span>Title <em>*</em></span>
              <input value={form.title} maxLength={255} required
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
            </label>
            <label className="mi-field">
              <span>Project <em>*</em></span>
              <select value={form.projectId} required
                onChange={(e) => setForm((f) => ({ ...f, projectId: e.target.value }))}>
                <option value="">Select a project…</option>
                {schedulableProjects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label className="mi-field">
              <span>Date &amp; time <em>*</em></span>
              <input type="datetime-local" value={form.scheduledAt} required
                onChange={(e) => setForm((f) => ({ ...f, scheduledAt: e.target.value }))} />
            </label>
            <label className="mi-field mi-field-wide">
              <span>Agenda (optional)</span>
              <textarea rows={2} value={form.description} maxLength={4000}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
            </label>
            {formError && <div className="mi-error mi-field-wide" role="alert">{formError}</div>}
            <div className="mi-upload-actions mi-field-wide">
              <button className="mi-btn mi-btn-primary" disabled={saving}>{saving ? 'Scheduling…' : 'Schedule'}</button>
              <button type="button" className="mi-btn mi-btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {error && <div className="mi-error" role="alert">{error}</div>}

      <div className="content-panel mi-panel">
        {loading ? (
          <p className="mi-muted">Loading…</p>
        ) : meetings.length === 0 ? (
          <p className="mi-empty">No scheduled meetings yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Title</th><th>Project</th><th>Organizer</th><th>When</th><th>Invited</th><th /></tr>
            </thead>
            <tbody>
              {meetings.map((m) => (
                <tr key={m.id}>
                  <td><strong>{m.title}</strong></td>
                  <td>{m.project_name}</td>
                  <td>{m.organizer_name}</td>
                  <td>{formatWhen(m.scheduled_at)}</td>
                  <td>{m.invitee_count}</td>
                  <td>
                    {m.organizer_user_id === myUserId ? (
                      <button className="mi-btn mi-btn-primary mi-btn-sm" disabled={starting === m.id}
                        onClick={() => handleStart(m)}>
                        {starting === m.id ? 'Starting…' : 'Start now'}
                      </button>
                    ) : (
                      <span className="mi-muted">Waiting for organizer</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
