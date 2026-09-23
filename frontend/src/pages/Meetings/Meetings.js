/**
 * pages/Meetings/Meetings.js
 *
 * Meeting Intelligence — connected to the FastAPI backend.
 *
 *   list view  : upload form (toggle) + meeting history (polls while processing)
 *   detail view: processing status, AI summary, transcript, action items, delete
 *
 * Uses component state for list/detail (the app only routes /meetings).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import '../Recruitment/Recruitment.css'; // shared .module-page / .content-panel / .badge
import './Meetings.css';

import AudioUpload from '../../modules/meetingIntelligence/AudioUpload';
import MeetingList from '../../modules/meetingIntelligence/MeetingList';
import TranscriptViewer from '../../modules/meetingIntelligence/TranscriptViewer';
import SummaryPanel from '../../modules/meetingIntelligence/SummaryPanel';
import ActionItemList from '../../modules/meetingIntelligence/ActionItemList';
import {
  deleteMeeting,
  getActionItems,
  getAnalysis,
  getMeeting,
  getTranscript,
  listMeetings,
  reprocessMeeting,
} from '../../api/meetingApi';
import {
  apiErrorMessage,
  formatDuration,
  isInProgress,
  statusBadge,
} from '../../modules/meetingIntelligence/helpers';

const LIST_POLL_MS = 6000;
const DETAIL_POLL_MS = 4000;

export default function Meetings() {
  const [meetings, setMeetings] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [showUpload, setShowUpload] = useState(false);

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [actionItems, setActionItems] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [deleting, setDeleting] = useState(false);

  // ---------------- list ----------------
  const loadList = useCallback(async () => {
    try {
      setMeetings(await listMeetings());
      setListError('');
    } catch (err) {
      setListError(apiErrorMessage(err, 'Could not load meeting history.'));
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId || !meetings.some((m) => isInProgress(m.status))) return undefined;
    const t = setInterval(loadList, LIST_POLL_MS);
    return () => clearInterval(t);
  }, [meetings, selectedId, loadList]);

  // ---------------- detail ----------------
  const loadResults = useCallback(async (id) => {
    const [tr, an, ai] = await Promise.allSettled([
      getTranscript(id),
      getAnalysis(id),
      getActionItems(id),
    ]);
    setTranscript(tr.status === 'fulfilled' ? tr.value : null);
    setAnalysis(an.status === 'fulfilled' ? an.value : null);
    setActionItems(ai.status === 'fulfilled' ? ai.value : []);
  }, []);

  const loadDetail = useCallback(
    async (id) => {
      try {
        const m = await getMeeting(id);
        setDetail(m);
        setDetailError('');
        // load whatever results exist (a failed meeting may still have a transcript)
        if (m.status === 'completed' || m.status === 'failed') await loadResults(id);
      } catch (err) {
        setDetailError(apiErrorMessage(err, 'Could not load this meeting.'));
      }
    },
    [loadResults],
  );

  const openMeeting = useCallback(
    async (id) => {
      setSelectedId(id);
      setShowUpload(false);
      setDetail(null);
      setTranscript(null);
      setAnalysis(null);
      setActionItems([]);
      setDetailLoading(true);
      await loadDetail(id);
      setDetailLoading(false);
    },
    [loadDetail],
  );

  const backToList = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
    setDetailError('');
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId || !detail || !isInProgress(detail.status)) return undefined;
    const t = setInterval(() => loadDetail(selectedId), DETAIL_POLL_MS);
    return () => clearInterval(t);
  }, [selectedId, detail, loadDetail]);

  async function handleUploaded(meeting) {
    setShowUpload(false);
    await loadList();
    openMeeting(meeting.id);
  }

  async function handleDelete() {
    if (!selectedId) return;
    // eslint-disable-next-line no-alert
    if (!window.confirm('Delete this meeting and all of its data? This cannot be undone.')) return;
    setDeleting(true);
    try {
      await deleteMeeting(selectedId);
      backToList();
    } catch (err) {
      setDetailError(apiErrorMessage(err, 'Delete failed.'));
    } finally {
      setDeleting(false);
    }
  }

  async function handleRetry() {
    if (!selectedId) return;
    try {
      const m = await reprocessMeeting(selectedId);
      setDetail(m); // status = pending -> polling resumes via the effect
      setDetailError('');
    } catch (err) {
      setDetailError(apiErrorMessage(err, 'Could not restart processing.'));
    }
  }

  // ---------------- render ----------------
  return (
    <div className="module-page mi-page">
      <div className="module-page-header">
        <div className="module-page-icon cyan" aria-hidden="true">🎙️</div>
        <div>
          <h1>Meeting Intelligence</h1>
          <p>
            Upload a recorded meeting and get an offline transcript, speaker
            breakdown, summary, decisions and action items.
          </p>
        </div>
      </div>

      <div className="mi-list-toolbar">
        <span>Offline Meeting</span>
        <Link className="mi-btn mi-btn-primary" to="/meetings/online">Open Online Meeting</Link>
      </div>

      {selectedId ? (
        <MeetingDetail
          meetingId={selectedId}
          detail={detail}
          detailLoading={detailLoading}
          detailError={detailError}
          transcript={transcript}
          analysis={analysis}
          actionItems={actionItems}
          deleting={deleting}
          onBack={backToList}
          onDelete={handleDelete}
          onRetry={handleRetry}
          onActionItemsChanged={() => loadResults(selectedId)}
        />
      ) : (
        <>
          <div className="mi-list-toolbar">
            <h2>Meeting history</h2>
            <button className="mi-btn mi-btn-primary" onClick={() => setShowUpload((v) => !v)}>
              {showUpload ? 'Close' : '+ Upload meeting'}
            </button>
          </div>

          {showUpload && (
            <div className="content-panel mi-panel">
              <AudioUpload onUploaded={handleUploaded} onCancel={() => setShowUpload(false)} />
            </div>
          )}

          {listError && <div className="mi-error" role="alert">{listError}</div>}

          <div className="content-panel mi-panel">
            <MeetingList
              meetings={meetings}
              loading={listLoading}
              selectedId={selectedId}
              onSelect={openMeeting}
            />
          </div>
        </>
      )}
    </div>
  );
}

function MeetingDetail({
  meetingId, detail, detailLoading, detailError, transcript, analysis, actionItems, onActionItemsChanged,
  deleting, onBack, onDelete, onRetry,
}) {
  const badge = detail ? statusBadge(detail.status) : null;
  const canRetry = detail && (detail.status === 'failed' || detail.status === 'completed');

  return (
    <>
      <button className="mi-back" onClick={onBack}>← Back to history</button>

      {detailLoading && !detail && <div className="mi-muted">Loading meeting…</div>}
      {detailError && <div className="mi-error" role="alert">{detailError}</div>}

      {detail && (
        <>
          <div className="mi-detail-head">
            <div>
              <h2 className="mi-detail-title">{detail.title}</h2>
              {detail.description && <p className="mi-detail-desc">{detail.description}</p>}
              <p className="mi-detail-sub">
                {formatDuration(detail.duration_sec)}
                {detail.source_video_filename ? ` · ${detail.source_video_filename}` : ''}
                {detail.language ? ` · ${detail.language}` : ''}
              </p>
            </div>
            <div className="mi-detail-actions">
              <span className={`badge ${badge.badge}`}>{badge.label}</span>
              {canRetry && (
                <button className="mi-btn mi-btn-ghost mi-btn-sm" onClick={onRetry}>
                  {detail.status === 'failed' ? 'Retry processing' : 'Re-process'}
                </button>
              )}
              <button
                className="mi-btn mi-btn-danger mi-btn-sm"
                onClick={onDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>

          {isInProgress(detail.status) && (
            <div className="mi-processing" role="status">
              <span className="mi-spinner" aria-hidden="true" />
              Processing — transcription, speaker detection and AI analysis are running.
              This page refreshes automatically.
            </div>
          )}

          {detail.status === 'failed' && (
            <div className="mi-error" role="alert">
              Processing failed: {detail.error_message || 'unknown error'}
              {' '}Anything below already completed — use “Retry processing” to run the rest.
            </div>
          )}

          {analysis && <SummaryPanel analysis={analysis} />}
          {transcript && <TranscriptViewer transcript={transcript} />}
          {analysis && (
            <ActionItemList meetingId={meetingId} items={actionItems} onAssigned={onActionItemsChanged} />
          )}
        </>
      )}
    </>
  );
}
