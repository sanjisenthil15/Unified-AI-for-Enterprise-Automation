"""
modules/chat/router.py

FastAPI router for the Manager Chat module.

Endpoints:
    GET  /chat/contacts                        — who the caller may message (any user)
    POST /chat/threads                          — find-or-create a thread with {other_user_id} (any user, validated)
    GET  /chat/threads                          — the caller's threads (any user)
    GET  /chat/threads/{id}/messages?since_id=  — poll for messages (either party)
    POST /chat/threads/{id}/messages            — send a message (either party)
    POST /chat/threads/{id}/read                — mark the other party's messages read (either party)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_user
from models.employee import Employee
from models.user import User

from modules.chat.schemas import ContactInfo, MessageResponse, OpenThreadRequest, SendMessageRequest, ThreadResponse
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
