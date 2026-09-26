import React from 'react';

/**
 * Real video/audio calling via Jitsi Meet's free public server — no API key,
 * no account, no backend infra. Config is passed via the URL hash, which
 * Jitsi reads on load; no extra script needed.
 *
 * This is a separate system from our own transcript pipeline below it: Jitsi
 * handles participants actually seeing/hearing each other (with its own
 * built-in participant tiles), while MicrophoneInput independently captures
 * audio for transcription. They're not wired together, so the browser will
 * prompt for microphone access twice — once for each.
 */
export default function VideoCall({ meetingId, displayName }) {
  const room = `UnifiedAIMeeting-${meetingId}`;
  const name = encodeURIComponent(displayName || 'Guest');
  const src = `https://meet.jit.si/${room}#userInfo.displayName="${name}"&config.prejoinPageEnabled=false`;

  return (
    <div className="content-panel mi-panel online-video">
      <h2>Video &amp; audio</h2>
      <p className="mi-muted">
        Powered by Jitsi Meet's free public server — this is a separate,
        third-party video call, independent from the transcript below.
      </p>
      <iframe
        title="Meeting video call"
        src={src}
        allow="camera; microphone; fullscreen; display-capture; autoplay"
        className="online-video-frame"
      />
    </div>
  );
}
