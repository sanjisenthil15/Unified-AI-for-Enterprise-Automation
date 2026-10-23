"""
modules/chat/router.py

FastAPI router for the Chat module — 1:1 Manager Chat (DMs) and
Discord-style project-scoped Groups/Channels.

Endpoints:
    GET    /chat/contacts                        — who the caller may message (any user)
    POST   /chat/threads                          — find-or-create a DM thread with {other_user_id} (any user, validated)
    GET    /chat/threads                          — the caller's DM threads (any user)
    GET    /chat/threads/{id}/messages?since_id=  — poll for DM messages (either party)
    POST   /chat/threads/{id}/messages            — send a DM message (either party)
    POST   /chat/threads/{id}/read                — mark the other DM party's messages read (either party)

    POST   /chat/groups                              — create a group (that project's team lead, or admin/hr_manager)
    GET    /chat/groups                               — the caller's groups
    GET    /chat/groups/{id}                          — group detail incl. members + channels (group members only)
    POST   /chat/groups/{id}/members                  — add a member (manager of that project)
    DELETE /chat/groups/{id}/members/{user_id}        — remove a member (manager of that project)
    POST   /chat/groups/{id}/channels                 — create a channel (any group member)
    GET    /chat/groups/{id}/channels                 — list channels (group members only)
    GET    /chat/channels/{id}/messages?since_id=     — poll for channel messages (group members only)
    POST   /chat/channels/{id}/messages               — send a channel message (group members only)
    POST   /chat/channels/{id}/read                   — bump the caller's group read-marker
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_employee_optional, get_current_user
from models.employee import Employee
from models.user import User

from modules.chat.schemas import (
    AddMemberRequest,
    ChannelCreate,
    ChannelInfo,
    ChannelMessageResponse,
    ContactInfo,
    GroupCreate,
    GroupDetailResponse,
    GroupResponse,
    MessageResponse,
    OpenThreadRequest,
    SendChannelMessageRequest,
    SendMessageRequest,
    ThreadResponse,
)
from modules.chat import service

router = APIRouter(prefix="/chat", tags=["Manager Chat"])


def _optional_employee(db: Session, current_user: User) -> Employee | None:
    return db.query(Employee).filter(Employee.user_id == current_user.id).first()


@router.get("/contacts", response_model=List[ContactInfo], summary="Who the caller may message")
def list_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_contacts(db, current_user, _optional_employee(db, current_user))


@router.post("/threads", response_model=ThreadResponse, summary="Find-or-create a thread with another user")
def open_thread(
    payload: OpenThreadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_employee = _optional_employee(db, current_user)
    thread = service.open_thread(db, current_user, current_employee, payload.other_user_id)
    return [t for t in service.list_threads(db, current_user, current_employee) if t["id"] == thread.id][0]


@router.get("/threads", response_model=List[ThreadResponse], summary="The caller's chat threads")
def list_threads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_threads(db, current_user, _optional_employee(db, current_user))


@router.get("/threads/{thread_id}/messages", response_model=List[MessageResponse], summary="Poll for messages in a thread")
def get_messages(
    thread_id: int,
    since_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_messages(db, current_user, _optional_employee(db, current_user), thread_id, since_id)


@router.post("/threads/{thread_id}/messages", response_model=MessageResponse, status_code=201, summary="Send a message")
def send_message(
    thread_id: int,
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.send_message(db, current_user, _optional_employee(db, current_user), thread_id, payload.body)


@router.post("/threads/{thread_id}/read", summary="Mark the other party's messages read")
def mark_thread_read(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = service.mark_thread_read(db, current_user, _optional_employee(db, current_user), thread_id)
    return {"marked_read": count}


# ------------------------------------------------------------------ #
# Groups & channels
# ------------------------------------------------------------------ #

@router.post("/groups", response_model=GroupResponse, status_code=status.HTTP_201_CREATED, summary="Create a group (that project's team lead, or admin/hr_manager)")
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    return service.create_group(db, current_user, current_employee, payload)


@router.get("/groups", response_model=List[GroupResponse], summary="The caller's groups")
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_groups(db, current_user)


@router.get("/groups/{group_id}", response_model=GroupDetailResponse, summary="Group detail (members only)")
def get_group_detail(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_group_detail(db, current_user, group_id)


@router.post("/groups/{group_id}/members", status_code=status.HTTP_204_NO_CONTENT, summary="Add a member (manager of that project)")
def add_member(
    group_id: int,
    payload: AddMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    service.add_member(db, current_user, current_employee, group_id, payload.user_id)


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a member (manager of that project)")
def remove_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    service.remove_member(db, current_user, current_employee, group_id, user_id)


@router.post("/groups/{group_id}/channels", response_model=ChannelInfo, status_code=status.HTTP_201_CREATED, summary="Create a channel (any group member)")
def create_channel(
    group_id: int,
    payload: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = service.create_channel(db, current_user, group_id, payload.name)
    return {"id": channel.id, "name": channel.name}


@router.get("/groups/{group_id}/channels", response_model=List[ChannelInfo], summary="List a group's channels (members only)")
def list_channels(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channels = service.list_channels(db, current_user, group_id)
    return [{"id": c.id, "name": c.name} for c in channels]


@router.get("/channels/{channel_id}/messages", response_model=List[ChannelMessageResponse], summary="Poll for messages in a channel")
def get_channel_messages(
    channel_id: int,
    since_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_channel_messages(db, current_user, channel_id, since_id)


@router.post("/channels/{channel_id}/messages", response_model=ChannelMessageResponse, status_code=status.HTTP_201_CREATED, summary="Send a channel message")
def send_channel_message(
    channel_id: int,
    payload: SendChannelMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.send_channel_message(db, current_user, channel_id, payload.body)


@router.post("/channels/{channel_id}/read", summary="Bump the caller's read-marker for this channel's group")
def mark_channel_read(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.mark_channel_read(db, current_user, channel_id)
    return {"ok": True}
