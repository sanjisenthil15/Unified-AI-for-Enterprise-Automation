import { useCallback, useEffect, useRef, useState } from 'react';
import { getOnlineMeeting, getOnlineTicket, onlineSocketUrl } from '../../api/onlineMeetingApi';

export function applyLiveEvent(session, event) {
  if (event.type === 'snapshot' || event.type === 'meeting_ended') return event.session;
  if (!session) return session;
  if (event.type === 'transcript') {
    if (session.transcript.some((s) => s.id === event.id)) return session;
    return { ...session, transcript: [...session.transcript, event] };
  }
  if (event.type === 'analysis') {
    return { ...session, analysis: event, analysis_status: 'ready', analysis_error: null };
  }
  if (event.type === 'analysis_status') return { ...session, analysis_status: event.status };
  if (event.type === 'error' && event.code === 'analysis_failed') {
    return { ...session, analysis_status: 'error', analysis_error: event.message };
  }
  return session;
}

export default function useLiveMeeting(id) {
  const [session, setSession] = useState(null);
  const [connection, setConnection] = useState('CONNECTING');
  const [error, setError] = useState('');
  const [speaker, setSpeaker] = useState('');
  const socket = useRef(null);
  const pending = useRef(new Map());
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!id) return undefined;
    let disposed = false;
    let reconnectTimer;
    let handshakeTimer;
    let heartbeat;
    let attempts = 0;
    let ended = false;
    const key = `online-client:${id}`;
    let cid = sessionStorage.getItem(key);
    if (!cid) {
      cid = crypto.randomUUID();
      sessionStorage.setItem(key, cid);
    }
    setSession(null);
    setError('');

    const rejectPending = (message) => {
      pending.current.forEach(({ reject, timer }) => {
        clearTimeout(timer);
        reject(new Error(message));
      });
      pending.current.clear();
    };

    function reconnect() {
      if (disposed || ended) return;
      rejectPending('Connection lost. Input acknowledgement is unknown; check the transcript before retrying.');
      if (attempts >= 5) {
        setConnection('ERROR');
        setError('Connection failed after five retries. Use Reconnect to try again.');
        return;
      }
      setConnection('RECONNECTING');
      reconnectTimer = setTimeout(connect, Math.min(1000 * (2 ** attempts++), 10000));
    }

    async function connect() {
      if (disposed) return;
      setConnection(attempts ? 'RECONNECTING' : 'CONNECTING');
      try {
        const snapshot = await getOnlineMeeting(id);
        if (disposed) return;
        setSession(snapshot);
        if (snapshot.status === 'ended') {
          ended = true;
          setConnection('ENDED');
          return;
        }
        const { ticket } = await getOnlineTicket(id);
        if (disposed) return;
        const ws = new WebSocket(onlineSocketUrl(id));
        socket.current = ws;
        handshakeTimer = setTimeout(() => ws.close(), 12000);
        ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', ticket }));
        ws.onmessage = ({ data }) => {
          if (disposed) return;
          let event;
          try { event = JSON.parse(data); } catch {
            setError('The backend returned an invalid WebSocket message.');
            return;
          }
          if (event.type === 'authenticated') {
            ws.send(JSON.stringify({ type: 'join', client_id: cid }));
          } else if (event.type === 'join') {
            clearTimeout(handshakeTimer);
            attempts = 0;
            setSpeaker(event.speaker);
            setConnection('CONNECTED');
            setError('');
            heartbeat = setInterval(() => {
              if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
            }, 25000);
          } else if (event.type === 'error') {
            setError(event.message);
          }
          if (event.message_id && pending.current.has(event.message_id)) {
            const entry = pending.current.get(event.message_id);
            clearTimeout(entry.timer);
            pending.current.delete(event.message_id);
            if (event.type === 'error') entry.reject(new Error(event.message));
            else if (event.type === 'ack') entry.resolve(event);
          }
          setSession((current) => applyLiveEvent(current, event));
          if (event.type === 'meeting_ended') {
            ended = true;
            setConnection('ENDED');
            ws.close(1000);
          }
        };
        ws.onerror = () => setError('WebSocket unavailable. Check that the backend is running.');
        ws.onclose = () => {
          clearTimeout(handshakeTimer);
          clearInterval(heartbeat);
          if (socket.current === ws) socket.current = null;
          reconnect();
        };
      } catch (err) {
        if (disposed) return;
        setError(err.response?.status === 404
          ? 'Meeting not found. In-memory meetings expire or disappear when the backend restarts.'
          : 'Cannot reach the meeting API. Check backend availability and authentication.');
        if ([401, 403, 404].includes(err.response?.status)) setConnection('ERROR');
        else reconnect();
      }
    }
    connect();
    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      clearTimeout(handshakeTimer);
      clearInterval(heartbeat);
      rejectPending('Left the live meeting page.');
      const ws = socket.current;
      socket.current = null;
      if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'leave' }));
        ws.close();
      }
    };
  }, [id, retry]);

  const sendInput = useCallback((event) => new Promise((resolve, reject) => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || connection !== 'CONNECTED') {
      reject(new Error('Connect to the meeting before sending input.'));
      return;
    }
    if (pending.current.size >= 2 || ws.bufferedAmount > 3_000_000) {
      reject(new Error('Processing is busy. Wait before sending another clip.'));
      return;
    }
    const messageId = event.message_id || crypto.randomUUID();
    const timer = setTimeout(() => {
      pending.current.delete(messageId);
      reject(new Error('Input acknowledgement timed out. Check transcript before retrying.'));
    }, 120000);
    pending.current.set(messageId, { resolve, reject, timer });
    ws.send(JSON.stringify({ ...event, message_id: messageId }));
  }), [connection]);

  const analyze = useCallback(() => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify({ type: 'analyze' }));
    }
  }, []);

  return { session, setSession, connection, speaker, error, setError, sendInput, analyze,
    reconnect: () => setRetry((value) => value + 1) };
}