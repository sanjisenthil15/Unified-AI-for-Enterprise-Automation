"""
modules/chat/schemas.py

Pydantic schemas for the Manager Chat module.
"""

from datetime import datetime
from typing import Optional

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
