/**
 * modules/meetingIntelligence/helpers.js
 *
 * Small pure helpers shared by the Meeting Intelligence components.
 */

/** Backend pipeline states that mean "still working". */
export const IN_PROGRESS_STATUSES = [
  'pending', 'processing', 'extracting_audio', 'transcribing', 'diarizing', 'analyzing',
];

export function isInProgress(status) {
  return IN_PROGRESS_STATUSES.includes(status);
}

/** Map a raw meeting status to a display label + badge colour class. */
export function statusBadge(status) {
  switch (status) {
    case 'completed':
      return { label: 'Completed', badge: 'green' };
    case 'failed':
      return { label: 'Failed', badge: 'red' };
    case 'pending':
      return { label: 'Queued', badge: 'purple' };
    case 'processing':
    case 'extracting_audio':
    case 'transcribing':
    case 'diarizing':
    case 'analyzing':
      return { label: 'Processing', badge: 'amber' };
    default:
      return { label: status || 'Unknown', badge: 'purple' };
  }
}

/** Seconds -> "1h 04m" / "12m 30s" / "45s". */
export function formatDuration(totalSeconds) {
  if (totalSeconds == null) return '—';
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m) return `${m}m ${String(sec).padStart(2, '0')}s`;
  return `${sec}s`;
}

/** Milliseconds -> "mm:ss" (or "h:mm:ss"). */
export function formatTimestamp(ms) {
  if (ms == null) return '00:00';
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Stable colour index for a speaker label like "Speaker 3" -> 2. */
export function speakerColorIndex(label) {
  const m = /(\d+)/.exec(label || '');
  const n = m ? parseInt(m[1], 10) : 1;
  return ((n - 1) % 6 + 6) % 6;
}

export function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

/** Best-effort extraction of a human message from an Axios error. */
export function apiErrorMessage(err, fallback = 'Something went wrong.') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return err?.message || fallback;
}
