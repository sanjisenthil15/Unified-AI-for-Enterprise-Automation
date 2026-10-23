"""
modules/chat/schemas.py

Pydantic schemas for the Chat module — 1:1 Manager Chat (DMs) and
Discord-style project-scoped Groups/Channels.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    user_id: int
    full_name: str
    role: str
    job_title: Optional[str] = None


class OpenThreadRequest(BaseModel):
    other_user_id: int


class SendMessageRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    id: int
    thread_id: int
    sender_user_id: Optional[int] = None
    body: str
    read_at: Optional[datetime] = None
    created_at: datetime


class ThreadResponse(BaseModel):
    id: int
    other_user_id: int
    other_user_name: str
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    unread_count: int


# ------------------------------------------------------------------ #
# Groups & channels
# ------------------------------------------------------------------ #

class GroupCreate(BaseModel):
    project_id: int
    name: str = Field(..., min_length=2, max_length=100)
    member_user_ids: List[int] = Field(default_factory=list)


class GroupMemberInfo(BaseModel):
    user_id: int
    full_name: str


class ChannelInfo(BaseModel):
    id: int
    name: str


class GroupResponse(BaseModel):
    id: int
    project_id: int
    project_name: str
    name: str
    member_count: int
    unread: bool
    created_at: datetime


class GroupDetailResponse(GroupResponse):
    members: List[GroupMemberInfo]
    channels: List[ChannelInfo]


class AddMemberRequest(BaseModel):
    user_id: int


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class SendChannelMessageRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class ChannelMessageResponse(BaseModel):
    id: int
    channel_id: int
    sender_user_id: Optional[int] = None
    sender_name: Optional[str] = None
    body: str
    created_at: datetime
