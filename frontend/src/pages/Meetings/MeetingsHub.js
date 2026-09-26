/**
 * pages/Meetings/MeetingsHub.js
 *
 * Landing page for the Meetings section — choose Offline (upload/record a
 * finished recording) or Online (a live session with real video/audio and
 * continuous transcription).
 */

import React from 'react';
import { Link } from 'react-router-dom';
import '../Recruitment/Recruitment.css';
import './MeetingsHub.css';

export default function MeetingsHub() {
  return (
    <div className="module-page mi-page">
      <div className="module-page-header">
        <div className="module-page-icon cyan" aria-hidden="true">🎙️</div>
        <div><h1>Meetings</h1><p>Choose how you want to capture this meeting.</p></div>
      </div>
      <div className="meetings-hub-grid">
        <Link to="/meetings/offline" className="content-panel mi-panel meetings-hub-card">
          <span className="meetings-hub-icon" aria-hidden="true">📁</span>
          <h2>Offline Meeting</h2>
          <p>Record a meeting or upload an existing audio/video file, then get a transcript, AI summary, and action items.</p>
        </Link>
        <Link to="/meetings/online" className="content-panel mi-panel meetings-hub-card">
          <span className="meetings-hub-icon" aria-hidden="true">📡</span>
          <h2>Online Meeting</h2>
          <p>Start a live session — real video/audio calling, a shared invite link, and continuous transcription as you talk.</p>
        </Link>
      </div>
    </div>
  );
}
