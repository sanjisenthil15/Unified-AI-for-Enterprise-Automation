# Online (Live) Meeting Intelligence

Prototype module: live meetings with near-real-time transcript, speaker labels,
and AI analysis (summary / decisions / action items). In-memory only — no
database tables, no Alembic migrations, no SQLAlchemy model changes. Ended
sessions stay in memory for 24 hours; a backend restart clears them. Run a
single Uvicorn worker.

## HTTP API (all under `/api/v1`, JWT auth via `core.dependencies.get_current_user`;
with `AUTH_DISABLED=true` every request acts as the seeded demo user)

### Start meeting
`POST /api/v1/meetings/online`

```json
{ "title": "Project team sync", "request_id": "3f9d3c58-...-uuid" }
```

`201 Created`:

```json
{
  "id": "18f2914d-0822-492b-bdee-307a1f6401e2",
  "title": "Project team sync",
  "status": "active",
  "started_at": "2026-09-17T18:30:00Z",
  "ended_at": null,
  "participants": [],
  "transcript": [],
  "analysis": null,
  "analysis_status": "idle",
  "analysis_error": null,
  "websocket_path": "/api/v1/meetings/online/18f2914d.../ws"
}
```

- `request_id` makes retries idempotent: the same id + title returns the same
  session; the same id with a different title is `409`.
- A second active session for the same user is `409` with
  `{"detail": {"message": ..., "meeting_id": ...}}` so the client can rejoin.
- `422` invalid body, `503` prototype capacity reached.

### Status
`GET /api/v1/meetings/online/{meeting_id}` → `200` session (shape above) or
`404` (unknown id, another user's session, or expired/pruned).

### End meeting
`POST /api/v1/meetings/online/{meeting_id}/end` → `200` session. Status moves
`active → ending → ended`; already-accepted audio finishes, a final analysis
runs, then `meeting_ended` is broadcast. Ending twice is safe (idempotent).
New input after end is rejected with a recoverable `error` event.

### WebSocket ticket
`POST /api/v1/meetings/online/{meeting_id}/ws-ticket` →
`{ "ticket": "...", "expires_in": 30 }`. Tickets are single-use, valid 30 s,
bound to the meeting, and never placed in URLs.

## WebSocket `GET /api/v1/meetings/online/{meeting_id}/ws`

Origin must be `http://localhost:3000` (or absent for non-browser clients).
First message within 10 s, otherwise close `1008`:

```json
{ "type": "auth", "ticket": "<ticket from ws-ticket>" }
```

Server: `{ "type": "authenticated" }`. Then `join` (required before meeting
events; `client_id` is a browser-generated UUID kept in `sessionStorage` so a
reconnect reuses the same speaker label):

```json
{ "type": "join", "client_id": "uuid" }
```

Server: `{ "type": "join", "speaker": "Speaker 1", "client_id": "uuid" }`
followed by a full `{ "type": "snapshot", "session": { ... } }`.

### Client → Server events
```json
{ "type": "transcript", "message_id": "uuid", "text": "We should finish the backend by Friday.", "start_ms": 12000, "end_ms": 14500 }
{ "type": "audio", "message_id": "uuid", "data": "<base64>", "mime_type": "audio/webm", "start_ms": 12000, "end_ms": 20000 }
{ "type": "analyze" }
{ "type": "leave" }
{ "type": "ping" }
```

Constraints: complete clips only (≤ 30 s, ≤ 2 MB decoded, one in flight per
client), `text` ≤ 4000 chars, unknown/extra fields rejected.

### Server → Client events
```json
{ "type": "transcript", "id": "uuid", "speaker": "Speaker 1", "text": "We should finish the backend by Friday.", "start_ms": 12000, "end_ms": 14500, "source": "audio" }
{ "type": "ack", "message_id": "uuid", "segment_count": 1 }
{ "type": "analysis_status", "status": "processing" }
{ "type": "analysis", "summary": "...", "key_points": [], "decisions": ["..."], "action_items": [{ "description": "Finish the frontend dashboard", "assignee": "Speaker 2", "priority": "high", "confidence": 0.9 }], "model_provider": "gemini", "model_name": "...", "transcript_count": 4, "generated_at": "..." }
{ "type": "decision", "index": 0, "transcript_count": 4, "description": "..." }
{ "type": "action_item", "index": 0, "transcript_count": 4, "description": "...", "assignee": "Speaker 2", "priority": "high", "confidence": 0.9 }
{ "type": "snapshot", "session": { ...full session... } }
{ "type": "join", "speaker": "Speaker 1", "client_id": "uuid" }
{ "type": "leave", "client_id": "uuid" }
{ "type": "meeting_ended", "session": { ...final session... } }
{ "type": "error", "code": "invalid_message|transcription_failed|analysis_failed|processing_failed", "message": "...", "message_id": "uuid?", "recoverable": true }
{ "type": "pong" }
```

`analysis`/`decision`/`action_item` events are revisions of the latest
analysis (keyed by `transcript_count`), not append-only records. Errors with
`recoverable: true` never terminate the session; the transcript is preserved.

## Transcription
Reuses the offline module's pure functions: browser clips (MediaRecorder,
one complete file at a time) are base64-decoded, normalized to 16 kHz mono WAV
by the bundled FFmpeg (`processing/audio.py`), then transcribed by the shared
faster-whisper model (`processing/transcription.py`) behind a lock. Failures
return a recoverable `transcription_failed` error; the session stays alive.

## Speakers
MVP labels are positional (`Speaker 1`, `Speaker 2`, …) per browser
`client_id`. No voice biometrics; no mapping to real users. A later phase can
map `Participant.client_id` to PostgreSQL users without protocol changes.

## AI analysis
Reuses the offline module's provider pattern
(`processing/analysis.py` → Gemini via `GEMINI_API_KEY`, model
`MEETING_GEMINI_MODEL`, default `gemini-flash-lite-latest`). Runs debounced
(~15 s) after new transcript, on demand (`analyze`), and once at meeting end.
On failure: `analysis_status = "error"`, a recoverable error event, transcript
preserved, retry via `analyze`. No keys are hardcoded or logged.

## Configuration / run
Backend needs `DATABASE_URL` (+ optional `GEMINI_API_KEY`); see
`backend/.env.example`. No new env vars and no new dependencies were added.

```bat
cd backend && .venv\Scripts\activate
uvicorn main:app --reload --port 8000
cd frontend && npm start   :: http://localhost:3000/meetings/online
```

## Tests
```bat
python -m pytest online_tests -q        # no DB or network required
```

## Known limitations
- In-memory single-process state; restart loses sessions; ended sessions
  pruned after 24 h.
- One active online meeting per user; 16 participants; 100 sessions; 2000
  inputs per meeting; transcript size capped by `analysis_max_transcript_chars`.
- Microphone capture records the local browser's microphone only (not remote
  participants' audio); one clip at a time, max 8 s per clip.
- Speaker labels are ordinal, not identities; assignees stay as heard.
- AI analysis requires a configured Gemini key; without it the meeting works
  and analysis reports a recoverable error.