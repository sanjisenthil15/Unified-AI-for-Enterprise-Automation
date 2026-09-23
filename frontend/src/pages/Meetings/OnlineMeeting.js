import React, { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { endOnlineMeeting, startOnlineMeeting } from '../../api/onlineMeetingApi';
import useLiveMeeting from '../../modules/meetingOnline/useLiveMeeting';
import MicrophoneInput from '../../modules/meetingOnline/MicrophoneInput';
import SummaryPanel from '../../modules/meetingIntelligence/SummaryPanel';
import { formatTimestamp } from '../../modules/meetingIntelligence/helpers';
import '../Recruitment/Recruitment.css';
import './Meetings.css';
import './OnlineMeeting.css';

export default function OnlineMeeting() {
  const [params, setParams] = useSearchParams();
  const id = params.get('session');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);

  async function start(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    if (!request.current || request.current.title !== title.trim()) {
      request.current = { title: title.trim(), id: crypto.randomUUID() };
    }
    try {
      const meeting = await startOnlineMeeting(request.current.title, request.current.id);
      setParams({ session: meeting.id });
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail?.meeting_id) {
        setParams({ session: detail.meeting_id });
      } else {
        setError(typeof detail === 'string' ? detail : 'Could not start meeting. Check backend availability and authentication, then retry.');
      }
    } finally { setBusy(false); }
  }

  return (
    <div className="module-page mi-page online-page">
      <div className="module-page-header">
        <div className="module-page-icon cyan" aria-hidden="true">🎙</div>
        <div><h1>Online Meeting</h1><p>Live transcript and meeting intelligence — college prototype.</p></div>
      </div>
      <nav className="online-toolbar" aria-label="Meeting modes">
        <Link className="mi-btn mi-btn-ghost" to="/meetings">Offline Meeting</Link>
        {id && <Link className="mi-btn mi-btn-ghost" to="/meetings/online">Start / resume meeting</Link>}
      </nav>
      <p className="mi-muted">Sessions are private to your signed-in account (shared demo account in development).
        Results stay in server memory for up to 24 hours after ending; a backend restart clears them.</p>
      {id ? <LiveSession key={id} id={id} /> : (
        <form className="content-panel mi-panel online-form" onSubmit={start}>
          <h2>Start a live session</h2>
          <label htmlFor="online-title">Meeting title</label>
          <input id="online-title" value={title} onChange={(e) => setTitle(e.target.value)}
            required maxLength={255} placeholder="Project team sync" />
          <p>Record short microphone clips or enter actual discussion text. Transcript text is sent to the configured AI provider for analysis.</p>
          {error && <div role="alert" className="mi-error">{error}</div>}
          <button className="mi-btn mi-btn-primary" disabled={busy || !title.trim()}>
            {busy ? 'Starting…' : 'Start meeting'}
          </button>
        </form>
      )}
    </div>
  );
}

function LiveSession({ id }) {
  const live = useLiveMeeting(id);
  const { session, connection, speaker, error, setError, sendInput } = live;
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [microphoneBusy, setMicrophoneBusy] = useState(false);
  const [ending, setEnding] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const active = session?.status === 'active';
  const connected = connection === 'CONNECTED';
  const elapsed = session ? Math.max(0, (session.ended_at ? Date.parse(session.ended_at) : clock) - Date.parse(session.started_at)) : 0;

  async function submit(event) {
    event.preventDefault();
    if (!text.trim() || sending) return;
    setSending(true);
    setError('');
    try {
      const timestamp = Math.max(0, Date.now() - Date.parse(session.started_at));
      await sendInput({ type: 'transcript', text: text.trim(), start_ms: timestamp, end_ms: timestamp });
      setText('');
    } catch (err) { setError(err.message); }
    finally { setSending(false); }
  }

  async function end() {
    setEnding(true);
    try { live.setSession(await endOnlineMeeting(id)); }
    catch { setError('Could not end meeting. Check the backend and retry; the session has not been discarded.'); }
    finally { setEnding(false); }
  }

  async function copyLink() {
    const link = `${window.location.origin}/meetings/online?session=${id}`;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Could not copy the link. Copy it from the address bar instead.');
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `online-meeting-${id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="content-panel mi-panel">
        <div className="online-toolbar">
          <h2>{session?.title || 'Loading session…'}</h2>
          <strong role="status">{connection}</strong>
          <span>{session?.status?.toUpperCase()} · {formatTimestamp(elapsed)}</span>
        </div>
        <p className="online-id">Session ID: {id}</p>
        <p>{speaker ? `Your label: ${speaker}. ` : ''}
          Anyone with an account can join from the invite link below.</p>
        <div className="online-toolbar">
          <button className="mi-btn mi-btn-ghost" onClick={copyLink}>
            {copied ? 'Link copied!' : '🔗 Copy invite link'}
          </button>
          {connection === 'ERROR' && <button className="mi-btn mi-btn-primary" onClick={live.reconnect}>Reconnect</button>}
          <button className="mi-btn mi-btn-danger" disabled={!active || ending || microphoneBusy || sending} onClick={end}>
            {ending || session?.status === 'ending' ? 'Finalizing meeting…' : 'End meeting'}
          </button>
          <button className="mi-btn mi-btn-ghost" disabled={!session} onClick={download}>Download results</button>
        </div>
        {session?.status === 'ending' && <p role="status">Finishing accepted input and final analysis. Transcript remains available.</p>}
        {session?.status === 'ended' && <p role="status">Meeting ended. Results are retained temporarily; download them to keep a copy.</p>}
      </div>
      {error && <div className="mi-error" role="alert">{error}</div>}
      {active && (
        <section className="content-panel mi-panel">
          <h2>Live input</h2>
          <MicrophoneInput disabled={!connected || !active} startedAt={session.started_at}
            sendInput={sendInput} onError={setError} onBusy={setMicrophoneBusy} />
          <form className="online-form" onSubmit={submit}>
            <label htmlFor="live-text">Manual transcript — actual discussion text, not simulated audio</label>
            <textarea id="live-text" value={text} onChange={(e) => setText(e.target.value)} maxLength={4000}
              rows={3} disabled={!connected || sending} placeholder="Enter what was said…" />
            <button className="mi-btn mi-btn-primary" disabled={!connected || sending || !text.trim()}>
              {sending ? 'Sending…' : 'Send transcript'}
            </button>
          </form>
        </section>
      )}
      <section className="content-panel mi-panel">
        <h2>Live transcript <span className="mi-count">{session?.transcript.length || 0}</span></h2>
        <ul className="online-participants" aria-label="Participants">
          {(session?.participants || []).map((p) => (
            <li key={p.client_id} className={p.connected ? 'is-online' : 'is-offline'}>
              <span className="online-dot" aria-hidden="true" />
              {p.speaker}{!p.connected && ' (left)'}
            </li>
          ))}
          {!session?.participants?.length && <li className="mi-muted">No participants yet.</li>}
        </ul>
        <div className="online-transcript" role="log" aria-label="Live transcript" aria-live="polite">
          {session?.transcript.length ? session.transcript.map((segment) => (
            <article key={segment.id}>
              <strong>{segment.speaker}</strong> <small>{formatTimestamp(segment.start_ms)} · {segment.source}</small>
              <p>{segment.text}</p>
            </article>
          )) : <p className="mi-muted">No transcript yet. Record a clip or enter discussion text.</p>}
        </div>
      </section>
      <section className="content-panel mi-panel">
        <div className="online-toolbar">
          <h2>AI insights</h2>
          <span role="status">{session?.analysis_status || 'idle'}</span>
          <button className="mi-btn mi-btn-ghost" onClick={live.analyze}
            disabled={!connected || !session?.transcript.length || session?.analysis_status === 'processing' || !active}>
            Analyze / retry
          </button>
        </div>
        <p className="mi-muted">Updated periodically and at meeting end. AI suggestions need human review.</p>
        {session?.analysis_error && <p role="alert">{session.analysis_error}</p>}
        {session?.analysis && <p>Analysis covers {session.analysis.transcript_count} of {session.transcript.length} segments.</p>}
      </section>
      {session?.analysis && <SummaryPanel analysis={session.analysis} />}
      <section className="content-panel mi-panel">
        <h2>Action items</h2>
        {session?.analysis?.action_items.length ? (
          <ul className="mi-action-items">{session.analysis.action_items.map((item, index) => (
            <li className="mi-action-item" key={index}>
              <strong>{item.description}</strong>
              <p>{item.assignee || 'No assignee mentioned'} · Priority: {item.priority || 'unspecified'}
                {item.confidence != null && ` · Confidence: ${Math.round(item.confidence * 100)}%`}</p>
            </li>
          ))}</ul>
        ) : <p className="mi-muted">No action items extracted yet. No employee assignments are made automatically.</p>}
      </section>
    </>
  );
}