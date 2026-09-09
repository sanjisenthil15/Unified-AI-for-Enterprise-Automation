/**
 * modules/meetingIntelligence/TranscriptViewer.js
 *
 * Diarized transcript: a speaker legend + timestamped, speaker-attributed lines.
 * Speaker labels are generic ("Speaker 1", ...) — mapping them to real people
 * is a future enhancement (needs a backend endpoint).
 */

import React from 'react';
import { formatDuration, formatTimestamp, speakerColorIndex } from './helpers';

export default function TranscriptViewer({ transcript }) {
  if (!transcript) return null;

  const { speakers = [], segments = [], full_text: fullText, language, whisper_model: model } = transcript;

  return (
    <section className="content-panel mi-panel">
      <h2>Transcript</h2>

      <div className="mi-transcript-meta">
        {language && <span>Language: <strong>{language}</strong></span>}
        {model && <span>Model: <strong>whisper {model}</strong></span>}
        {segments.length > 0 && <span><strong>{segments.length}</strong> segments</span>}
      </div>

      {speakers.length > 0 && (
        <div className="mi-speakers" aria-label="Speakers">
          {speakers.map((s) => (
            <span key={s.id} className={`mi-speaker-chip mi-spk-${speakerColorIndex(s.label)}`}>
              <span className="mi-speaker-dot" aria-hidden="true" />
              {s.display_name || s.label}
              {s.segment_count != null && (
                <em>
                  {' '}· {s.segment_count} turn{s.segment_count === 1 ? '' : 's'}
                  {s.total_speaking_sec ? ` · ${formatDuration(s.total_speaking_sec)}` : ''}
                </em>
              )}
            </span>
          ))}
        </div>
      )}

      {segments.length > 0 ? (
        <div className="mi-transcript">
          {segments.map((seg) => (
            <div key={seg.seq} className="mi-line">
              <span className="mi-line-time">{formatTimestamp(seg.start_ms)}</span>
              <span className={`mi-line-speaker mi-spk-${speakerColorIndex(seg.speaker_label)}`}>
                {seg.speaker_label || 'Speaker'}
              </span>
              <span className="mi-line-text">{seg.text}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="mi-plain-transcript">{fullText}</p>
      )}
    </section>
  );
}
