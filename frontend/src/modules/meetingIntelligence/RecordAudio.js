/**
 * modules/meetingIntelligence/RecordAudio.js
 *
 * In-browser microphone recorder for the offline upload form — an
 * alternative to picking a file. Records continuously (manual start/stop,
 * no time limit) and hands the parent a real File so it flows through the
 * same upload path as a picked file.
 */

import React, { useEffect, useRef, useState } from 'react';

function formatElapsed(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const seconds = String(totalSeconds % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

export default function RecordAudio({ disabled, onRecorded, onError }) {
  const [state, setState] = useState('idle');
  const [elapsed, setElapsed] = useState(0);
  const recorder = useRef(null);
  const stream = useRef(null);
  const startedAt = useRef(0);
  const tick = useRef(null);
  const mounted = useRef(true);

  function release() {
    clearInterval(tick.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      release();
    };
  }, []);

  async function start() {
    setState('permission');
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
        throw new Error('Microphone recording is unavailable in this browser. Upload a file instead.');
      }
      const mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
        .find((value) => MediaRecorder.isTypeSupported(value));
      if (!mime) throw new Error('No supported recording format. Upload a file instead.');
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const current = new MediaRecorder(media, { mimeType: mime });
      recorder.current = current;
      const chunks = [];
      current.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      current.onerror = () => {
        release();
        if (mounted.current) {
          setState('idle');
          onError('Microphone recording failed. Try again or upload a file.');
        }
      };
      current.onstop = () => {
        release();
        if (!mounted.current) return;
        const blob = new Blob(chunks, { type: mime });
        if (!blob.size) {
          setState('idle');
          onError('No audio was recorded.');
          return;
        }
        const extension = mime.startsWith('audio/webm') ? '.webm' : mime.startsWith('audio/ogg') ? '.ogg' : '.mp4';
        const file = new File([blob], `recording-${Date.now()}${extension}`, { type: mime.split(';')[0] });
        setState('idle');
        onRecorded(file);
      };
      current.start();
      startedAt.current = Date.now();
      setElapsed(0);
      tick.current = setInterval(() => setElapsed(Date.now() - startedAt.current), 250);
      setState('recording');
    } catch (err) {
      release();
      if (mounted.current) {
        setState('idle');
        onError(err.name === 'NotAllowedError' ? 'Microphone permission denied.' : err.message);
      }
    }
  }

  return (
    <div className="mi-record">
      <button
        type="button"
        className="mi-btn mi-btn-ghost"
        disabled={disabled || state === 'permission'}
        onClick={() => (state === 'recording' ? recorder.current.stop() : start())}
      >
        {state === 'recording' ? `Stop recording (${formatElapsed(elapsed)})`
          : state === 'permission' ? 'Waiting for microphone…' : '🎙 Record instead'}
      </button>
    </div>
  );
}
