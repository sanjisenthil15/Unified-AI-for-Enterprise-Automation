import React, { useEffect, useRef, useState } from 'react';

export function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Could not read the recorded clip.'));
    reader.readAsDataURL(blob);
  });
}

const CLIP_MS = 8000;
const RETRY_DELAY_MS = 2000;

/**
 * Continuously transcribes while the meeting is active: records an ~8s
 * clip, sends it, and immediately starts the next one — no button press
 * per clip. A Mute toggle is the only manual control, since recording is
 * now automatic rather than opt-in.
 */
export default function MicrophoneInput({ disabled, startedAt, sendInput, onError, onBusy }) {
  const [state, setState] = useState('idle');
  const [muted, setMuted] = useState(false);
  const recorder = useRef(null);
  const stream = useRef(null);
  const timer = useRef(null);
  const retryTimer = useRef(null);
  const mounted = useRef(true);
  const cancelled = useRef(false);
  const mutedRef = useRef(false);
  const disabledRef = useRef(disabled);

  useEffect(() => { mutedRef.current = muted; }, [muted]);
  useEffect(() => { disabledRef.current = disabled; }, [disabled]);

  function release() {
    clearTimeout(timer.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  function scheduleNext() {
    clearTimeout(retryTimer.current);
    if (disabledRef.current || mutedRef.current || !mounted.current) return;
    retryTimer.current = setTimeout(() => {
      if (mounted.current && !disabledRef.current && !mutedRef.current) start();
    }, RETRY_DELAY_MS);
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancelled.current = true;
      clearTimeout(retryTimer.current);
      if (recorder.current?.state === 'recording') recorder.current.stop();
      release();
    };
  }, []);

  // Start listening as soon as it's enabled; stop when disabled or muted.
  useEffect(() => {
    if (disabled || muted) {
      clearTimeout(retryTimer.current);
      if (recorder.current?.state === 'recording') {
        cancelled.current = true;
        recorder.current.stop();
        release();
      }
      return;
    }
    if (recorder.current?.state !== 'recording' && state === 'idle') start();
  }, [disabled, muted]);

  async function start() {
    if (recorder.current?.state === 'recording') return;
    cancelled.current = false;
    setState('permission');
    onBusy(true);
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
        throw new Error('Microphone recording is unavailable. Use localhost/HTTPS or manual transcript input.');
      }
      const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
        .find((value) => MediaRecorder.isTypeSupported(value));
      if (!mime) throw new Error('No supported recording format. Use manual transcript input.');
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current || cancelled.current) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const current = new MediaRecorder(media, { mimeType: mime, audioBitsPerSecond: 64000 });
      recorder.current = current;
      const chunks = [];
      const startMs = Math.max(0, Date.now() - Date.parse(startedAt));
      current.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      current.onerror = () => {
        cancelled.current = true;
        release();
        if (mounted.current) {
          setState('idle');
          onBusy(false);
          onError('Microphone recording failed. Retrying…');
          scheduleNext();
        }
      };
      current.onstop = async () => {
        const endMs = Math.max(startMs, Date.now() - Date.parse(startedAt));
        release();
        if (!mounted.current) return;
        if (cancelled.current) {
          setState('idle');
          onBusy(false);
          return;
        }
        setState('processing');
        try {
          const blob = new Blob(chunks, { type: mime });
          if (blob.size) {
            await sendInput({
              type: 'audio', data: await blobToBase64(blob),
              mime_type: mime.split(';')[0], start_ms: startMs, end_ms: endMs,
            });
          }
        } catch (err) {
          if (mounted.current) onError(err.message);
        } finally {
          if (mounted.current) {
            setState('idle');
            onBusy(false);
            if (!disabledRef.current && !mutedRef.current) start();
          }
        }
      };
      current.start(); // Each stop produces a complete, independently decodable file.
      setState('recording');
      timer.current = setTimeout(() => {
        if (current.state === 'recording') current.stop();
      }, CLIP_MS);
    } catch (err) {
      release();
      if (mounted.current) {
        setState('idle');
        onBusy(false);
        onError(err.name === 'NotAllowedError' ? 'Microphone permission denied. You can still enter transcript text.' : err.message);
        scheduleNext();
      }
    }
  }

  return (
    <div className="online-microphone">
      <button type="button" className="mi-btn mi-btn-ghost" disabled={disabled}
        onClick={() => setMuted((m) => !m)}>
        {muted ? '🔇 Muted — click to resume' : '🔴 Listening — click to mute'}
      </button>
      <p role="status">
        {muted ? 'Not transcribing. Click above to resume.'
          : state === 'processing' ? 'Transcribing the last clip…'
          : 'Continuously transcribing in ~8s clips while you talk — no button needed.'}
      </p>
    </div>
  );
}
