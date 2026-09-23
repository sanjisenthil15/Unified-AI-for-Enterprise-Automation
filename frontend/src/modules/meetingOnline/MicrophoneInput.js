import React, { useEffect, useRef, useState } from 'react';

export function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Could not read the recorded clip.'));
    reader.readAsDataURL(blob);
  });
}

export default function MicrophoneInput({ disabled, startedAt, sendInput, onError, onBusy }) {
  const [state, setState] = useState('idle');
  const recorder = useRef(null);
  const stream = useRef(null);
  const timer = useRef(null);
  const mounted = useRef(true);
  const cancelled = useRef(false);

  function release() {
    clearTimeout(timer.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancelled.current = true;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      release();
    };
  }, []);

  useEffect(() => {
    if (disabled && recorder.current?.state === 'recording') {
      cancelled.current = true;
      recorder.current.stop();
      release();
    }
  }, [disabled]);

  async function start() {
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
          onError('Microphone recording failed. Try again or enter text.');
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
          if (!blob.size) throw new Error('No audio was recorded.');
          await sendInput({
            type: 'audio', data: await blobToBase64(blob),
            mime_type: mime.split(';')[0], start_ms: startMs, end_ms: endMs,
          });
        } catch (err) {
          if (mounted.current) onError(err.message);
        } finally {
          if (mounted.current) {
            setState('idle');
            onBusy(false);
          }
        }
      };
      current.start(); // Each stop produces a complete, independently decodable file.
      setState('recording');
      timer.current = setTimeout(() => {
        if (current.state === 'recording') current.stop();
      }, 8000);
    } catch (err) {
      release();
      if (mounted.current) {
        setState('idle');
        onBusy(false);
        onError(err.name === 'NotAllowedError' ? 'Microphone permission denied. You can still enter transcript text.' : err.message);
      }
    }
  }

  return (
    <div className="online-microphone">
      <button type="button" className="mi-btn mi-btn-primary"
        disabled={disabled || state === 'permission' || state === 'processing'}
        onClick={() => state === 'recording' ? recorder.current.stop() : start()}>
        {state === 'recording' ? 'Stop and send clip' : state === 'processing'
          ? 'Transcribing clip…' : state === 'permission' ? 'Waiting for microphone…' : 'Record microphone clip'}
      </button>
      <p role="status">{state === 'recording' ? 'Recording — stops automatically after 8 seconds.' :
        'One clip at a time. Only your microphone is captured, not remote meeting audio. Obtain participant consent.'}</p>
    </div>
  );
}