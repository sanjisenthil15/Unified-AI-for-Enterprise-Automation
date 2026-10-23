"""
modules/chat/service.py

Business logic for the Manager Chat module.

Deliberately scoped to the manager relationship (team lead <-> their
project's members, or admin/hr_manager <-> anyone) — not a general
company-wide DM. See core/authorization.py for the underlying rule.
"""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from core.authorization import assert_project_manager, is_team_lead_of
from models.chat_channel import ChatChannel
from models.chat_channel_message import ChatChannelMessage
from models.chat_group import ChatGroup
from models.chat_group_member import ChatGroupMember
from models.employee import Employee
from models.manager_chat_message import ManagerChatMessage
from models.manager_chat_thread import ManagerChatThread
from models.project import Project
from models.user import User

from modules.notifications.service import create_notification

_OVERRIDE_ROLES = ("admin", "hr_manager")


# ------------------------------------------------------------------ #
# Contacts
# ------------------------------------------------------------------ #

def list_contacts(db: Session, current_user: User, current_employee: Employee | None) -> list[dict]:
    contacts: list[dict] = []
    seen_user_ids: set[int] = {current_user.id}

    if current_user.role.name in _OVERRIDE_ROLES:
        employees = db.query(Employee).options(joinedload(Employee.user)).filter(Employee.deleted_at.is_(None)).all()
        for emp in employees:
            if emp.user_id in seen_user_ids:
                continue
            seen_user_ids.add(emp.user_id)
            contacts.append({
                "user_id": emp.user_id, "full_name": emp.user.full_name,
                "role": emp.user.role.name, "job_title": emp.job_title,
            })
        return contacts

    if current_employee is not None:
        # Reports (employees this person leads, if they're a team lead of any project).
        led_employees = (
            db.query(Employee)
            .join(Employee.project)
            .options(joinedload(Employee.user))
            .filter(Employee.project.has(team_lead_id=current_employee.id), Employee.deleted_at.is_(None))
            .all()
        )
        for emp in led_employees:
            if emp.user_id in seen_user_ids:
                continue
            seen_user_ids.add(emp.user_id)
            contacts.append({
                "user_id": emp.user_id, "full_name": emp.user.full_name,
                "role": emp.user.role.name, "job_title": emp.job_title,
            })

        # Own team lead.
        if current_employee.project is not None and current_employee.project.team_lead is not None:
            lead = current_employee.project.team_lead
            if lead.user_id not in seen_user_ids:
                seen_user_ids.add(lead.user_id)
                contacts.append({
                    "user_id": lead.user_id, "full_name": lead.user.full_name,
                    "role": lead.user.role.name, "job_title": lead.job_title,
                })

    # Everyone can always reach admin/hr_manager.
    admins = db.query(User).options(joinedload(User.role)).filter(User.deleted_at.is_(None)).all()
    for user in admins:
        if user.role.name in _OVERRIDE_ROLES and user.id not in seen_user_ids:
            seen_user_ids.add(user.id)
            contacts.append({"user_id": user.id, "full_name": user.full_name, "role": user.role.name, "job_title": None})

    return contacts


def can_open_chat(db: Session, current_user: User, current_employee: Employee | None, other_user_id: int) -> bool:
    if current_user.role.name in _OVERRIDE_ROLES:
        return True
    other_user = db.query(User).filter(User.id == other_user_id).first()
    if other_user is not None and other_user.role.name in _OVERRIDE_ROLES:
        return True
    if current_employee is None:
        return False
    other_employee = db.query(Employee).filter(Employee.user_id == other_user_id).first()
    if other_employee is None:
        return False
    return is_team_lead_of(db, current_employee, other_employee) or is_team_lead_of(db, other_employee, current_employee)


def _resolve_thread_parties(db: Session, current_user: User, current_employee: Employee | None, other_user_id: int) -> tuple[int, int]:
    """Returns (employee_id, manager_user_id) — the "subject" employee is
    always the non-manager side, so the pair normalizes the same way
    regardless of who opened the thread first."""
    other_user = db.query(User).filter(User.id == other_user_id).first()
    if other_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"User id={other_user_id} not found.")

    current_is_manager = current_user.role.name in _OVERRIDE_ROLES
    other_is_manager = other_user.role.name in _OVERRIDE_ROLES

    other_employee = db.query(Employee).filter(Employee.user_id == other_user_id).first()
    if not current_is_manager and current_employee is not None and other_employee is not None:
        if is_team_lead_of(db, current_employee, other_employee):
            current_is_manager = True
    if not other_is_manager and current_employee is not None and other_employee is not None:
        if is_team_lead_of(db, other_employee, current_employee):
            other_is_manager = True

    if current_is_manager and other_employee is not None:
        return other_employee.id, current_user.id
    if other_is_manager and current_employee is not None:
        return current_employee.id, other_user.id
    raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only message your own team lead, your project's members, or admin/HR.")


# ------------------------------------------------------------------ #
# Threads
# ------------------------------------------------------------------ #

def _thread_other_party(thread: ManagerChatThread, current_user_id: int) -> tuple[int, str]:
    if thread.manager_user_id == current_user_id:
        return thread.employee.user_id, thread.employee.user.full_name
    return thread.manager_user_id, thread.manager_user.full_name


def _is_party(thread: ManagerChatThread, current_user: User, current_employee: Employee | None) -> bool:
    if thread.manager_user_id == current_user.id:
        return True
    return current_employee is not None and thread.employee_id == current_employee.id


def open_thread(db: Session, current_user: User, current_employee: Employee | None, other_user_id: int) -> ManagerChatThread:
    employee_id, manager_user_id = _resolve_thread_parties(db, current_user, current_employee, other_user_id)
    thread = (
        db.query(ManagerChatThread)
        .filter(ManagerChatThread.employee_id == employee_id, ManagerChatThread.manager_user_id == manager_user_id)
        .first()
    )
    if thread is None:
        thread = ManagerChatThread(employee_id=employee_id, manager_user_id=manager_user_id)
        db.add(thread)
        db.commit()
        db.refresh(thread)
    return thread


def list_threads(db: Session, current_user: User, current_employee: Employee | None) -> list[dict]:
    query = db.query(ManagerChatThread).options(
        joinedload(ManagerChatThread.employee).joinedload(Employee.user),
        joinedload(ManagerChatThread.manager_user),
    )
    if current_employee is not None:
        threads = query.filter(
            (ManagerChatThread.manager_user_id == current_user.id)
            | (ManagerChatThread.employee_id == current_employee.id)
        ).all()
    else:
        threads = query.filter(ManagerChatThread.manager_user_id == current_user.id).all()

    results = []
    for thread in threads:
        other_user_id, other_user_name = _thread_other_party(thread, current_user.id)
        last_message = (
            db.query(ManagerChatMessage)
            .filter(ManagerChatMessage.thread_id == thread.id)
            .order_by(ManagerChatMessage.created_at.desc())
            .first()
        )
        unread_count = (
            db.query(ManagerChatMessage)
            .filter(
                ManagerChatMessage.thread_id == thread.id,
                ManagerChatMessage.read_at.is_(None),
                ManagerChatMessage.sender_user_id != current_user.id,
            )
            .count()
        )
        results.append({
            "id": thread.id,
            "other_user_id": other_user_id,
            "other_user_name": other_user_name,
            "last_message": last_message.body if last_message else None,
            "last_message_at": last_message.created_at if last_message else thread.created_at,
            "unread_count": unread_count,
        })
    results.sort(key=lambda r: r["last_message_at"], reverse=True)
    return results


def _get_thread_for_party(db: Session, current_user: User, current_employee: Employee | None, thread_id: int) -> ManagerChatThread:
    thread = (
        db.query(ManagerChatThread)
        .options(joinedload(ManagerChatThread.employee).joinedload(Employee.user), joinedload(ManagerChatThread.manager_user))
        .filter(ManagerChatThread.id == thread_id)
        .first()
    )
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Chat thread id={thread_id} not found.")
    if not _is_party(thread, current_user, current_employee):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You're not a party to this chat thread.")
    return thread


def get_messages(db: Session, current_user: User, current_employee: Employee | None, thread_id: int, since_id: int | None) -> list[ManagerChatMessage]:
    thread = _get_thread_for_party(db, current_user, current_employee, thread_id)
    query = db.query(ManagerChatMessage).filter(ManagerChatMessage.thread_id == thread.id)
    if since_id is not None:
        query = query.filter(ManagerChatMessage.id > since_id)
    return query.order_by(ManagerChatMessage.created_at).all()


def send_message(db: Session, current_user: User, current_employee: Employee | None, thread_id: int, body: str) -> ManagerChatMessage:
    thread = _get_thread_for_party(db, current_user, current_employee, thread_id)
    message = ManagerChatMessage(thread_id=thread.id, sender_user_id=current_user.id, body=body)
    db.add(message)
    db.commit()
    db.refresh(message)

    other_user_id, _ = _thread_other_party(thread, current_user.id)
    if other_user_id is not None:
        create_notification(db, other_user_id, "chat_message", f"New message from {current_user.full_name}.", "/chat")

    return message


def mark_thread_read(db: Session, current_user: User, current_employee: Employee | None, thread_id: int) -> int:
    thread = _get_thread_for_party(db, current_user, current_employee, thread_id)
    updated = (
        db.query(ManagerChatMessage)
        .filter(
            ManagerChatMessage.thread_id == thread.id,
            ManagerChatMessage.read_at.is_(None),
            ManagerChatMessage.sender_user_id != current_user.id,
        )
        .update({"read_at": datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
    return updated


# ------------------------------------------------------------------ #
# Groups & channels
# ------------------------------------------------------------------ #

def _get_group_or_404(db: Session, group_id: int) -> ChatGroup:
    group = db.query(ChatGroup).filter(ChatGroup.id == group_id).first()
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Chat group id={group_id} not found.")
    return group


def _assert_group_member(db: Session, group: ChatGroup, current_user: User) -> ChatGroupMember | None:
    """Raises 403 unless the caller is an actual member of this group, or
    admin/hr_manager (the same standing override used everywhere else in
    this app — attendance, sprints, review — for viewing a team they're
    not literally staffed on). Returns None for an override caller who
    has no real ChatGroupMember row; every caller only uses the return
    value for the assertion's side effect, not its content."""
    if current_user.role.name in _OVERRIDE_ROLES:
        return None
    member = (
        db.query(ChatGroupMember)
        .filter(ChatGroupMember.group_id == group.id, ChatGroupMember.user_id == current_user.id)
        .first()
    )
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You're not a member of this group.")
    return member


def _group_response(db: Session, group: ChatGroup, current_user: User) -> dict:
    project = group.project or db.query(Project).filter(Project.id == group.project_id).first()
    member = (
        db.query(ChatGroupMember)
        .filter(ChatGroupMember.group_id == group.id, ChatGroupMember.user_id == current_user.id)
        .first()
    )
    unread = False
    if member is not None:
        last_message = (
            db.query(ChatChannelMessage)
            .join(ChatChannel)
            .filter(ChatChannel.group_id == group.id)
            .order_by(ChatChannelMessage.created_at.desc())
            .first()
        )
        if last_message is not None and (member.last_read_at is None or last_message.created_at > member.last_read_at):
            unread = True
    return {
        "id": group.id,
        "project_id": group.project_id,
        "project_name": project.name if project else "",
        "name": group.name,
        "member_count": db.query(ChatGroupMember).filter(ChatGroupMember.group_id == group.id).count(),
        "unread": unread,
        "created_at": group.created_at,
    }


def create_group(db: Session, current_user: User, current_employee: Employee | None, payload) -> dict:
    assert_project_manager(db, current_user, current_employee, payload.project_id)

    group = ChatGroup(project_id=payload.project_id, name=payload.name, created_by_user_id=current_user.id)
    db.add(group)
    db.flush()

    db.add(ChatChannel(group_id=group.id, name="general", created_by_user_id=current_user.id))

    member_ids = set(payload.member_user_ids) | {current_user.id}
    for user_id in member_ids:
        db.add(ChatGroupMember(group_id=group.id, user_id=user_id))

    db.commit()
    db.refresh(group)

    for user_id in member_ids:
        if user_id != current_user.id:
            create_notification(db, user_id, "chat_group_created", f"You were added to the group '{group.name}'.", f"/chat?group={group.id}")

    return _group_response(db, group, current_user)


def list_groups(db: Session, current_user: User) -> list[dict]:
    query = db.query(ChatGroup).options(joinedload(ChatGroup.project))
    if current_user.role.name in _OVERRIDE_ROLES:
        # Standing override, same as attendance/sprints/review: see every
        # group, not just ones they were explicitly added to.
        groups = query.order_by(ChatGroup.name).all()
    else:
        group_ids = [
            m.group_id for m in db.query(ChatGroupMember).filter(ChatGroupMember.user_id == current_user.id).all()
        ]
        if not group_ids:
            return []
        groups = query.filter(ChatGroup.id.in_(group_ids)).all()
    return [_group_response(db, g, current_user) for g in groups]


def get_group_detail(db: Session, current_user: User, group_id: int) -> dict:
    group = _get_group_or_404(db, group_id)
    _assert_group_member(db, group, current_user)

    members = (
        db.query(ChatGroupMember)
        .options(joinedload(ChatGroupMember.user))
        .filter(ChatGroupMember.group_id == group.id)
        .all()
    )
    channels = db.query(ChatChannel).filter(ChatChannel.group_id == group.id).order_by(ChatChannel.created_at).all()

    base = _group_response(db, group, current_user)
    base["members"] = [{"user_id": m.user_id, "full_name": m.user.full_name} for m in members]
    base["channels"] = [{"id": c.id, "name": c.name} for c in channels]
    return base


def add_member(db: Session, current_user: User, current_employee: Employee | None, group_id: int, user_id: int) -> None:
    group = _get_group_or_404(db, group_id)
    assert_project_manager(db, current_user, current_employee, group.project_id)

    existing = (
        db.query(ChatGroupMember)
        .filter(ChatGroupMember.group_id == group.id, ChatGroupMember.user_id == user_id)
        .first()
    )
    if existing is not None:
        return
    target_user = db.query(User).filter(User.id == user_id).first()
    if target_user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"User id={user_id} does not exist.")

    db.add(ChatGroupMember(group_id=group.id, user_id=user_id))
    db.commit()
    create_notification(db, user_id, "chat_group_member_added", f"You were added to the group '{group.name}'.", f"/chat?group={group.id}")


def remove_member(db: Session, current_user: User, current_employee: Employee | None, group_id: int, user_id: int) -> None:
    group = _get_group_or_404(db, group_id)
    assert_project_manager(db, current_user, current_employee, group.project_id)
    db.query(ChatGroupMember).filter(
        ChatGroupMember.group_id == group.id, ChatGroupMember.user_id == user_id,
    ).delete()
    db.commit()


def create_channel(db: Session, current_user: User, group_id: int, name: str) -> ChatChannel:
    group = _get_group_or_404(db, group_id)
    _assert_group_member(db, group, current_user)

    existing = db.query(ChatChannel).filter(ChatChannel.group_id == group.id, ChatChannel.name == name).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A channel named '{name}' already exists in this group.")

    channel = ChatChannel(group_id=group.id, name=name, created_by_user_id=current_user.id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def list_channels(db: Session, current_user: User, group_id: int) -> list[ChatChannel]:
    group = _get_group_or_404(db, group_id)
    _assert_group_member(db, group, current_user)
    return db.query(ChatChannel).filter(ChatChannel.group_id == group.id).order_by(ChatChannel.created_at).all()


def _get_channel_for_member(db: Session, current_user: User, channel_id: int) -> ChatChannel:
    channel = db.query(ChatChannel).options(joinedload(ChatChannel.group)).filter(ChatChannel.id == channel_id).first()
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Channel id={channel_id} not found.")
    _assert_group_member(db, channel.group, current_user)
    return channel


def _channel_message_response(message: ChatChannelMessage) -> dict:
    return {
        "id": message.id,
        "channel_id": message.channel_id,
        "sender_user_id": message.sender_user_id,
        "sender_name": message.sender.full_name if message.sender else None,
        "body": message.body,
        "created_at": message.created_at,
    }


def get_channel_messages(db: Session, current_user: User, channel_id: int, since_id: int | None) -> list[dict]:
    channel = _get_channel_for_member(db, current_user, channel_id)
    query = (
        db.query(ChatChannelMessage)
        .options(joinedload(ChatChannelMessage.sender))
        .filter(ChatChannelMessage.channel_id == channel.id)
    )
    if since_id is not None:
        query = query.filter(ChatChannelMessage.id > since_id)
    messages = query.order_by(ChatChannelMessage.created_at).all()
    return [_channel_message_response(m) for m in messages]


def send_channel_message(db: Session, current_user: User, channel_id: int, body: str) -> dict:
    channel = _get_channel_for_member(db, current_user, channel_id)
    message = ChatChannelMessage(channel_id=channel.id, sender_user_id=current_user.id, body=body)
    db.add(message)
    db.commit()
    db.refresh(message)
    message = (
        db.query(ChatChannelMessage).options(joinedload(ChatChannelMessage.sender))
        .filter(ChatChannelMessage.id == message.id).first()
    )
    return _channel_message_response(message)


def mark_channel_read(db: Session, current_user: User, channel_id: int) -> None:
    channel = _get_channel_for_member(db, current_user, channel_id)
    member = (
        db.query(ChatGroupMember)
        .filter(ChatGroupMember.group_id == channel.group_id, ChatGroupMember.user_id == current_user.id)
        .first()
    )
    if member is not None:
        member.last_read_at = datetime.utcnow()
        db.commit()
