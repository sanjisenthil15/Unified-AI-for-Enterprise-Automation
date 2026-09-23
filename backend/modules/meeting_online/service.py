"""Single-process, owner-scoped online sessions with replaceable processors.

Run one Uvicorn worker. Ended sessions are retained for 24 hours; restart clears
everything. No ORM imports or persistence side effects belong in this service.
"""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import HTTPException, WebSocket

from modules.meeting_intelligence.config import meeting_settings
from modules.meeting_online import processing
from modules.meeting_online.schemas import (
    OnlineMeetingSession, Participant, TranscriptSegment, now,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    owner_id: int
    request_id: str
    view: OnlineMeetingSession
    sockets: dict[str, WebSocket] = field(default_factory=dict)
    seen: set[str] = field(default_factory=set)
    input_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    analysis_task: asyncio.Task | None = None
    last_analysis: float = 0
    end_task: asyncio.Task | None = None


class OnlineMeetingService:
    def __init__(self, transcriber=None, analyzer=None):
        self.sessions: dict[str, SessionState] = {}
        self.tickets: dict[str, tuple[str, float]] = {}
        self.transcriber = transcriber or processing.transcribe_chunk
        self.analyzer = analyzer or processing.analyze_transcript
        self.audio_slots = asyncio.Semaphore(2)

    def prune(self):
        for key, state in list(self.sessions.items()):
            if state.view.ended_at and (now() - state.view.ended_at).total_seconds() > 86400:
                if not state.sockets:
                    del self.sessions[key]
        self.tickets = {k: v for k, v in self.tickets.items() if v[1] > time.monotonic()}

    def create(self, owner_id, request):
        self.prune()
        for state in self.sessions.values():
            if state.owner_id != owner_id:
                continue
            if state.request_id == str(request.request_id):
                if state.view.title != request.title:
                    raise HTTPException(409, "request_id was already used with a different title.")
                return state.view
            if state.view.status != "ended":
                raise HTTPException(409, {
                    "message": "An online meeting is already active.",
                    "meeting_id": state.view.id,
                })
        if len(self.sessions) >= 100:
            raise HTTPException(503, "Prototype session capacity reached. Try later.")
        mid = str(uuid4())
        view = OnlineMeetingSession(
            id=mid, title=request.title,
            websocket_path=f"/api/v1/meetings/online/{mid}/ws",
        )
        self.sessions[mid] = SessionState(owner_id, str(request.request_id), view)
        return view

    def get(self, mid, owner_id=None):
        self.prune()
        state = self.sessions.get(mid)
        if state is None or (owner_id is not None and state.owner_id != owner_id):
            raise HTTPException(404, "Online meeting not found or expired.")
        return state

    def ticket(self, mid, user_id, full_name):
        # Any authenticated user who has the (unguessable) meeting id may
        # request a ticket — joining a meeting you didn't create is the
        # whole point of sharing a link. Only host actions (end) stay
        # owner-gated via get(mid, owner_id).
        self.get(mid)
        self.prune()
        if len(self.tickets) >= 1000:
            raise HTTPException(429, "Too many pending connections.")
        token = secrets.token_urlsafe(32)
        self.tickets[token] = (mid, time.monotonic() + 30, user_id, full_name)
        return {"ticket": token, "expires_in": 30}

    def consume_ticket(self, mid, token):
        value = self.tickets.pop(token, None)
        if not value or value[0] != mid or value[1] <= time.monotonic():
            return None
        return {"user_id": value[2], "full_name": value[3]}

    async def send(self, state, ws, event):
        async with state.send_lock:
            await asyncio.wait_for(ws.send_json(event), timeout=5)

    async def broadcast(self, state, event):
        for cid, ws in list(state.sockets.items()):
            try:
                await self.send(state, ws, event)
            except (Exception,):
                if state.sockets.get(cid) is ws:
                    state.sockets.pop(cid, None)
                    for participant in state.view.participants:
                        if participant.client_id == cid:
                            participant.connected = False

    async def snapshot(self, state):
        await self.broadcast(state, {"type": "snapshot", "session": state.view.model_dump(mode="json")})

    async def join(self, state, cid, ws, display_name=None):
        if cid in state.sockets:
            raise ValueError("This client is already connected in another socket.")
        participant = next((p for p in state.view.participants if p.client_id == cid), None)
        if participant is None:
            if len(state.view.participants) >= 16:
                raise ValueError("Prototype speaker limit reached (16).")
            label = display_name or f"Speaker {len(state.view.participants) + 1}"
            participant = Participant(client_id=cid, speaker=label)
            state.view.participants.append(participant)
        elif display_name:
            participant.speaker = display_name
        participant.connected = True
        state.sockets[cid] = ws
        await self.send(state, ws, {"type": "join", "speaker": participant.speaker, "client_id": cid})
        await self.snapshot(state)
        return participant.speaker

    async def leave(self, state, cid, ws):
        if state.sockets.get(cid) is not ws:
            return
        state.sockets.pop(cid, None)
        for participant in state.view.participants:
            if participant.client_id == cid:
                participant.connected = False
        await self.broadcast(state, {"type": "leave", "client_id": cid})
        await self.snapshot(state)

    async def input(self, state, speaker, event):
        async with state.input_lock:
            if state.view.status != "active":
                raise ValueError("Meeting is no longer accepting input.")
            mid = str(event.message_id)
            if mid in state.seen:
                return {"type": "ack", "message_id": mid, "duplicate": True}
            if len(state.seen) >= 2000:
                raise ValueError("Prototype input limit reached. End this meeting.")
            if event.type == "audio":
                try:
                    async with self.audio_slots:
                        result = await asyncio.to_thread(self.transcriber, event.data, event.mime_type)
                    segments = [
                        TranscriptSegment(
                            id=f"{mid}:{index}", speaker=speaker, text=seg.text.strip(),
                            start_ms=min(event.end_ms, event.start_ms + seg.start_ms),
                            end_ms=min(event.end_ms, event.start_ms + max(seg.start_ms, seg.end_ms)),
                            source="audio",
                        )
                        for index, seg in enumerate(result.segments) if seg.text.strip()
                    ]
                except Exception:
                    logger.warning("Online transcription failed (%s); session preserved.", state.view.id)
                    return {"type": "error", "code": "transcription_failed", "message_id": mid,
                            "message": "Could not transcribe this clip. Retry or enter transcript text.",
                            "recoverable": True}
            else:
                segments = [TranscriptSegment(
                    id=mid, speaker=speaker, text=event.text,
                    start_ms=event.start_ms, end_ms=event.end_ms, source="manual",
                )]
            size = sum(len(s.speaker) + len(s.text) + 3 for s in state.view.transcript + segments)
            if size > meeting_settings.analysis_max_transcript_chars:
                raise ValueError("Transcript capacity reached. End this meeting before starting another.")
            state.seen.add(mid)
            state.view.transcript.extend(segments)
            for segment in segments:
                await self.broadcast(state, {"type": "transcript", **segment.model_dump()})
            if segments:
                self.schedule_analysis(state)
            return {"type": "ack", "message_id": mid, "segment_count": len(segments)}

    def schedule_analysis(self, state, immediate=False):
        if not state.view.transcript:
            return
        if state.analysis_task and not state.analysis_task.done():
            return
        state.analysis_task = asyncio.create_task(self._analysis(state, immediate))

    async def _analysis(self, state, immediate):
        if not immediate:
            await asyncio.sleep(max(0, 15 - (time.monotonic() - state.last_analysis)))
        segments = list(state.view.transcript)
        state.view.analysis_status = "processing"
        state.view.analysis_error = None
        await self.broadcast(state, {"type": "analysis_status", "status": "processing"})
        try:
            result = await asyncio.wait_for(asyncio.to_thread(self.analyzer, segments), timeout=60)
            state.view.analysis = result
            state.view.analysis_status = "ready"
            await self.broadcast(state, {"type": "analysis", **result.model_dump(mode="json")})
            # These events refer to the replacement analysis revision, not append-only records.
            for index, decision in enumerate(result.decisions):
                await self.broadcast(state, {"type": "decision", "index": index,
                                            "transcript_count": len(segments), "description": decision})
            for index, item in enumerate(result.action_items):
                await self.broadcast(state, {"type": "action_item", "index": index,
                                            "transcript_count": len(segments), **item.model_dump()})
        except Exception:
            logger.warning("Online analysis failed (%s); transcript preserved.", state.view.id)
            state.view.analysis_status = "error"
            state.view.analysis_error = (
                "AI analysis unavailable. Check GEMINI_API_KEY and MEETING_GEMINI_MODEL "
                "on the backend, or retry later. Transcript is preserved."
            )
            await self.broadcast(state, {"type": "error", "code": "analysis_failed",
                                        "message": state.view.analysis_error, "recoverable": True})
        finally:
            state.last_analysis = time.monotonic()
            await self.snapshot(state)
        # Input may have arrived while the provider was busy.
        if len(state.view.transcript) > len(segments) and state.view.status == "active":
            state.analysis_task = asyncio.create_task(self._analysis(state, False))

    def end(self, state):
        if state.view.status == "active":
            # Reject new input immediately. Already accepted audio finishes first.
            state.view.status = "ending"
            state.end_task = asyncio.create_task(self._end(state))
        return state.view

    async def _end(self, state):
        await self.snapshot(state)
        async with state.input_lock:
            pass
        if state.analysis_task and not state.analysis_task.done():
            await state.analysis_task
        analyzed = state.view.analysis.transcript_count if state.view.analysis else 0
        if state.view.transcript and analyzed < len(state.view.transcript):
            await self._analysis(state, True)
        state.view.status = "ended"
        state.view.ended_at = now()
        await self.broadcast(state, {"type": "meeting_ended", "session": state.view.model_dump(mode="json")})

    async def shutdown(self):
        tasks = []
        for state in self.sessions.values():
            tasks.extend(t for t in (state.analysis_task, state.end_task) if t and not t.done())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


service = OnlineMeetingService()