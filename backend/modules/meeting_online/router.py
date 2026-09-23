"""Authenticated HTTP routes and ticket-authenticated WebSocket transport."""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from config.settings import settings
from core.dependencies import get_current_user
from modules.meeting_online.schemas import ClientEvent, OnlineMeetingSession, StartMeeting
from modules.meeting_online.service import service


@asynccontextmanager
async def lifespan(app):
    yield
    await service.shutdown()


router = APIRouter(prefix="/meetings/online", tags=["Online Meeting"], lifespan=lifespan)


@router.post("", response_model=OnlineMeetingSession, status_code=201)
async def start_meeting(payload: StartMeeting, user=Depends(get_current_user)):
    return service.create(user.id, payload)


@router.get("/{meeting_id}", response_model=OnlineMeetingSession)
async def status_meeting(meeting_id: str, user=Depends(get_current_user)):
    # Any authenticated user with the link may view/join — not just the
    # creator. Only ending the meeting stays owner-only, below.
    return service.get(meeting_id).view


@router.post("/{meeting_id}/end", response_model=OnlineMeetingSession)
async def end_meeting(meeting_id: str, user=Depends(get_current_user)):
    return service.end(service.get(meeting_id, user.id))


@router.post("/{meeting_id}/ws-ticket")
async def websocket_ticket(meeting_id: str, user=Depends(get_current_user)):
    return service.ticket(meeting_id, user.id, user.full_name)


@router.websocket("/{meeting_id}/ws")
async def live_socket(ws: WebSocket, meeting_id: str):
    # Match the same allowed origins as CORS (settings.CORS_ORIGINS).
    # Non-browser API clients may omit Origin but must still present a
    # ticket. Never place tickets in URLs.
    if ws.headers.get("origin") not in (None, *settings.cors_origins_list):
        await ws.close(code=1008)
        return
    await ws.accept()
    state = None
    cid = None
    speaker = None
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
        auth = json.loads(raw) if len(raw) <= 1024 else {}
        if not isinstance(auth, dict) or auth.get("type") != "auth":
            await ws.close(code=1008)
            return
        token = auth.get("ticket")
        identity = service.consume_ticket(meeting_id, token) if isinstance(token, str) else None
        if identity is None:
            await ws.close(code=1008)
            return
        state = service.get(meeting_id)
        await service.send(state, ws, {"type": "authenticated"})
        while True:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=120)
            message_id = None
            try:
                if len(raw) > 2_801_000:
                    raise ValueError("Message exceeds the maximum size.")
                event = ClientEvent.model_validate_json(raw)
                message_id = str(event.message_id) if event.message_id else None
                if event.type == "join":
                    if cid is not None:
                        raise ValueError("Already joined.")
                    candidate = str(event.client_id)
                    speaker = await service.join(state, candidate, ws, identity["full_name"])
                    cid = candidate
                elif event.type == "ping":
                    await service.send(state, ws, {"type": "pong"})
                elif cid is None:
                    raise ValueError("Join before sending meeting events.")
                elif event.type == "leave":
                    await service.leave(state, cid, ws)
                    cid = None
                    await ws.close(code=1000)
                    return
                elif event.type == "analyze":
                    if state.view.status == "ending":
                        raise ValueError("Final analysis is already running.")
                    service.schedule_analysis(state, immediate=True)
                else:
                    result = await service.input(state, speaker, event)
                    await service.send(state, ws, result)
            except (ValidationError, ValueError):
                await service.send(state, ws, {
                    "type": "error", "code": "invalid_message", "message_id": message_id,
                    "message": "Invalid event or state. Check the Online Meeting protocol and session status.",
                    "recoverable": True,
                })
            except WebSocketDisconnect:
                raise
            except Exception:
                await service.send(state, ws, {
                    "type": "error", "code": "processing_failed", "message_id": message_id,
                    "message": "This event could not be processed. The meeting is preserved.",
                    "recoverable": True,
                })
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (asyncio.TimeoutError, ValueError, HTTPException):
        try:
            await ws.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if state is not None and cid is not None:
            await service.leave(state, cid, ws)