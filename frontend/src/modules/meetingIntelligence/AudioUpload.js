/**
 * modules/meetingIntelligence/AudioUpload.js
 *
 * Upload form for a recorded meeting (video or audio file).
 * On success, calls `onUploaded(meeting)` with the created meeting
 * (status = "pending"); the parent then starts polling for progress.
 */

import React, { useRef, useState } from 'react';
import { ACCEPTED_EXTENSIONS, uploadMeeting } from '../../api/meetingApi';
import { apiErrorMessage } from './helpers';

const MAX_MB = 1024;

function extensionOf(name) {
  const i = (name || '').lastIndexOf('.');
  return i >= 0 ? name.slice(i).toLowerCase() : '';
}

export default function AudioUpload({ onUploaded, onCancel }) {
  const fileRef = useRef(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [fileName, setFileName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    const file = fileRef.current?.files?.[0];
    if (!title.trim()) return setError('Please enter a meeting title.');
    if (!file) return setError('Please choose a recording to upload.');

    const ext = extensionOf(file.name);
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      return setError(`Unsupported file type "${ext || '(none)'}". Allowed: ${ACCEPTED_EXTENSIONS.join(', ')}`);
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      return setError(`File is larger than the ${MAX_MB} MB limit.`);
    }

    setSubmitting(true);
    try {
      const meeting = await uploadMeeting({
        title: title.trim(),
        description: description.trim() || undefined,
        meetingDate: meetingDate || undefined,
        file,
      });
      onUploaded?.(meeting);
    } catch (err) {
      setError(apiErrorMessage(err, 'Upload failed. Please try again.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="mi-upload" onSubmit={handleSubmit} aria-label="Upload meeting recording">
      <div className="mi-upload-grid">
        <label className="mi-field">
          <span>Meeting title <em>*</em></span>
          <input
            type="text"
            value={title}
            maxLength={255}
            placeholder="Q3 Product Roadmap Review"
            onChange={(e) => setTitle(e.target.value)}
            disabled={submitting}
          />
        </label>

        <label className="mi-field">
          <span>Meeting date</span>
          <input
            type="datetime-local"
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
            disabled={submitting}
          />
        </label>

        <label className="mi-field mi-field-wide">
          <span>Description</span>
          <textarea
            rows={2}
            value={description}
            maxLength={4000}
            placeholder="Optional context for this meeting"
            onChange={(e) => setDescription(e.target.value)}
            disabled={submitting}
          />
        </label>

        <label className="mi-field mi-field-wide">
          <span>Recording <em>*</em></span>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(',')}
            onChange={(e) => setFileName(e.target.files?.[0]?.name || '')}
            disabled={submitting}
          />
          {fileName && <small className="mi-file-name">{fileName}</small>}
        </label>
      </div>

      {error && <div className="mi-error" role="alert">{error}</div>}

      <div className="mi-upload-actions">
        <button type="submit" className="mi-btn mi-btn-primary" disabled={submitting}>
          {submitting ? 'Uploading…' : 'Upload & process'}
        </button>
        {onCancel && (
          <button type="button" className="mi-btn mi-btn-ghost" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
        )}
      </div>
      <p className="mi-hint">
        After upload, transcription, speaker detection and AI analysis run in the
        background. The meeting appears in your history immediately with a live status.
      </p>
    </form>
  );
}
