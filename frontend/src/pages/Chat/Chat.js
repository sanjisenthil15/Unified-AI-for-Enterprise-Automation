/**
 * pages/Chat/Chat.js
 *
 * Discord-style chat: Groups (project-scoped, manager-created, with
 * multiple topic Channels) + personal 1:1 Direct Messages, side by side.
 * Polling-based, same idiom as pages/Meetings/Meetings.js.
 *
 * `activeConversation` is a small discriminated union so one poller/
 * sender/bubble-renderer serves both kinds:
 *   { kind: 'dm',      id, otherUserId, otherUserName }
 *   { kind: 'channel', id, groupId, groupName, channelName }
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  createChannel, createGroup, deleteChannel, deleteGroup, getChannelMessages, getContacts, getGroupDetail,
  getMessages, listGroups, listThreads, markChannelRead, markThreadRead,
  openThread, sendChannelMessage, sendMessage,
} from '../../api/chatApi';
import { getMyEmployeeRecord, listProjects } from '../../api/employeeApi';
import { getTeamAttendance } from '../../api/attendanceApi';
import { getLedProjects } from '../../utils/teamLead';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './Chat.css';

const LIST_POLL_MS = 15000;
const MESSAGE_POLL_MS = 4000;

function currentUserId() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.id ?? null;
  } catch {
    return null;
  }
}

function currentRole() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.role?.name?.toLowerCase() ?? '';
  } catch {
    return '';
  }
}

export default function Chat() {
  const [searchParams, setSearchParams] = useSearchParams();
  const myUserId = currentUserId();
  const isOverride = ['admin', 'hr_manager'].includes(currentRole());

  const [contacts, setContacts] = useState([]);
  const [threads, setThreads] = useState([]);
  const [groups, setGroups] = useState([]);
  const [error, setError] = useState('');

  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [channels, setChannels] = useState([]);
  const [newChannelName, setNewChannelName] = useState('');

  const [activeConversation, setActiveConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const lastMessageIdRef = useRef(null);
  const messagesEndRef = useRef(null);

  const [showNewGroupForm, setShowNewGroupForm] = useState(false);
  const [myEmployee, setMyEmployee] = useState(null);
  const [ledProjects, setLedProjects] = useState([]);
  const [allProjects, setAllProjects] = useState([]);
  const [newGroupForm, setNewGroupForm] = useState({ projectId: '', name: '' });
  const [newGroupMembers, setNewGroupMembers] = useState([]); // candidate employees for the picked project
  const [selectedMemberIds, setSelectedMemberIds] = useState([]);

  const loadLists = useCallback(async () => {
    try {
      const [contactList, threadList, groupList] = await Promise.all([getContacts(), listThreads(), listGroups()]);
      setContacts(contactList);
      setThreads(threadList);
      setGroups(groupList);
    } catch {
      setError('Could not load your contacts.');
    }
  }, []);

  useEffect(() => {
    loadLists();
    const t = setInterval(loadLists, LIST_POLL_MS);
    return () => clearInterval(t);
  }, [loadLists]);

  useEffect(() => {
    getMyEmployeeRecord().then(setMyEmployee).catch(() => {});
    listProjects().then(setAllProjects).catch(() => {});
  }, []);

  useEffect(() => {
    if (myEmployee) setLedProjects(getLedProjects(myEmployee.id, allProjects));
  }, [myEmployee, allProjects]);

  const canCreateGroup = isOverride || ledProjects.length > 0;
  const groupProjectOptions = isOverride ? allProjects : ledProjects;
  const ledProjectIds = ledProjects.map((p) => p.id);

  function isManagerOfGroup(group) {
    return isOverride || ledProjectIds.includes(group?.project_id);
  }

  // ── Direct messages ────────────────────────────────────────────
  const openWithUser = useCallback(async (otherUserId) => {
    try {
      const thread = await openThread(otherUserId);
      setSelectedGroupId(null);
      setActiveConversation({ kind: 'dm', id: thread.id, otherUserId: thread.other_user_id, otherUserName: thread.other_user_name });
      setMessages([]);
      lastMessageIdRef.current = null;
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not open this conversation.');
    }
  }, []);

  // Deep-link support: /chat?with={userId} (Sprints' Team Review "Message" button).
  useEffect(() => {
    const withUserId = searchParams.get('with');
    if (withUserId) {
      openWithUser(Number(withUserId));
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line
  }, []);

  // ── Groups & channels ──────────────────────────────────────────
  async function openGroup(groupId) {
    setSelectedGroupId(groupId);
    setActiveConversation(null);
    try {
      const detail = await getGroupDetail(groupId);
      setChannels(detail.channels);
    } catch {
      setError('Could not open this group.');
    }
  }

  function openChannel(channel) {
    const group = groups.find((g) => g.id === selectedGroupId);
    setActiveConversation({
      kind: 'channel', id: channel.id, groupId: selectedGroupId,
      groupName: group?.name || '', channelName: channel.name,
    });
    setMessages([]);
    lastMessageIdRef.current = null;
  }

  async function handleCreateChannel(e) {
    e.preventDefault();
    if (!newChannelName.trim() || !selectedGroupId) return;
    try {
      await createChannel(selectedGroupId, newChannelName.trim());
      setNewChannelName('');
      const detail = await getGroupDetail(selectedGroupId);
      setChannels(detail.channels);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create channel.');
    }
  }

  async function handleProjectPickedForGroup(projectId) {
    setNewGroupForm((f) => ({ ...f, projectId }));
    setSelectedMemberIds([]);
    if (!projectId) { setNewGroupMembers([]); return; }
    try {
      const entries = await getTeamAttendance({ projectId: Number(projectId) });
      setNewGroupMembers(entries.map((e) => e.employee));
    } catch {
      setNewGroupMembers([]);
    }
  }

  async function handleCreateGroup(e) {
    e.preventDefault();
    if (!newGroupForm.projectId || !newGroupForm.name.trim()) return;
    try {
      const memberUserIds = newGroupMembers.filter((m) => selectedMemberIds.includes(m.id)).map((m) => m.user_id);
      const group = await createGroup({
        projectId: Number(newGroupForm.projectId), name: newGroupForm.name.trim(), memberUserIds,
      });
      setShowNewGroupForm(false);
      setNewGroupForm({ projectId: '', name: '' });
      setNewGroupMembers([]);
      setSelectedMemberIds([]);
      await loadLists();
      openGroup(group.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create group.');
    }
  }

  async function handleDeleteChannel(e, channelId) {
    e.stopPropagation();
    if (!window.confirm('Delete this channel and all its messages?')) return;
    try {
      await deleteChannel(channelId);
      if (activeConversation?.kind === 'channel' && activeConversation.id === channelId) setActiveConversation(null);
      const detail = await getGroupDetail(selectedGroupId);
      setChannels(detail.channels);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not delete channel.');
    }
  }

  async function handleDeleteGroup(e, groupId) {
    e.stopPropagation();
    if (!window.confirm('Delete this group, all its channels, and all messages? This cannot be undone.')) return;
    try {
      await deleteGroup(groupId);
      if (selectedGroupId === groupId) {
        setSelectedGroupId(null);
        setChannels([]);
        setActiveConversation(null);
      }
      await loadLists();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not delete group.');
    }
  }

  // ── Messages (shared between DM and channel) ───────────────────
  const pollMessages = useCallback(async () => {
    if (!activeConversation) return;
    try {
      const newMessages = activeConversation.kind === 'dm'
        ? await getMessages(activeConversation.id, lastMessageIdRef.current)
        : await getChannelMessages(activeConversation.id, lastMessageIdRef.current);
      if (newMessages.length) {
        setMessages((prev) => [...prev, ...newMessages]);
        lastMessageIdRef.current = newMessages[newMessages.length - 1].id;
        if (activeConversation.kind === 'dm') markThreadRead(activeConversation.id).catch(() => {});
        else markChannelRead(activeConversation.id).catch(() => {});
      }
    } catch {
      // transient — next poll will retry
    }
  }, [activeConversation]);

  useEffect(() => {
    if (!activeConversation) return undefined;
    pollMessages();
    const t = setInterval(pollMessages, MESSAGE_POLL_MS);
    return () => clearInterval(t);
  }, [activeConversation, pollMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    if (!draft.trim() || !activeConversation) return;
    try {
      const msg = activeConversation.kind === 'dm'
        ? await sendMessage(activeConversation.id, draft.trim())
        : await sendChannelMessage(activeConversation.id, draft.trim());
      setMessages((prev) => [...prev, msg]);
      lastMessageIdRef.current = msg.id;
      setDraft('');
      loadLists();
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not send message.');
    }
  }

  function threadForContact(userId) {
    return threads.find((t) => t.other_user_id === userId);
  }

  return (
    <div className="module-page">
      <div className="module-page-header">
        <div className="module-page-icon purple" aria-hidden="true">💬</div>
        <div><h1>Team Chat</h1><p>Group discussions for your project, plus direct messages.</p></div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="chat-layout">
        <div className="chat-contacts">
          <div className="chat-sidebar-section">
            <div className="chat-sidebar-heading">
              Groups
              {canCreateGroup && (
                <button className="chat-sidebar-add" onClick={() => setShowNewGroupForm((v) => !v)} aria-label="New group">
                  {showNewGroupForm ? '×' : '+'}
                </button>
              )}
            </div>

            {showNewGroupForm && (
              <form className="chat-new-group-form" onSubmit={handleCreateGroup}>
                <select className="field-select" value={newGroupForm.projectId}
                  onChange={(e) => handleProjectPickedForGroup(e.target.value)} required>
                  <option value="">Select a project…</option>
                  {groupProjectOptions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <input className="field-input" placeholder="Group name" value={newGroupForm.name}
                  onChange={(e) => setNewGroupForm((f) => ({ ...f, name: e.target.value }))} required />
                {newGroupMembers.length > 0 && (
                  <div className="chat-member-picker">
                    {newGroupMembers.map((m) => (
                      <label key={m.id} className="chat-member-picker-item">
                        <input type="checkbox" checked={selectedMemberIds.includes(m.id)}
                          onChange={(e) => setSelectedMemberIds((ids) => (
                            e.target.checked ? [...ids, m.id] : ids.filter((id) => id !== m.id)
                          ))} />
                        {m.full_name}
                      </label>
                    ))}
                  </div>
                )}
                <button type="submit" className="btn-primary">Create group</button>
              </form>
            )}

            {groups.length === 0 && !showNewGroupForm && (
              <p className="chat-empty-hint">No groups yet.</p>
            )}
            {groups.map((g) => (
              <div key={g.id}
                className={`chat-contact-item${selectedGroupId === g.id ? ' active' : ''}`}
                onClick={() => openGroup(g.id)}>
                <div>
                  <div className="chat-contact-name"># {g.name}</div>
                  <div className="chat-contact-role">{g.project_name}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  {g.unread && <span className="chat-unread-dot" aria-label="Unread messages" />}
                  {isManagerOfGroup(g) && (
                    <button className="chat-delete-btn" title="Delete group"
                      onClick={(e) => handleDeleteGroup(e, g.id)}>🗑</button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="chat-sidebar-section">
            <div className="chat-sidebar-heading">Direct Messages</div>
            {contacts.length === 0 && <p className="chat-empty-hint">No contacts yet.</p>}
            {contacts.map((c) => {
              const thread = threadForContact(c.user_id);
              return (
                <div
                  key={c.user_id}
                  className={`chat-contact-item${activeConversation?.kind === 'dm' && activeConversation.otherUserId === c.user_id ? ' active' : ''}`}
                  onClick={() => openWithUser(c.user_id)}
                >
                  <div>
                    <div className="chat-contact-name">{c.full_name}</div>
                    <div className="chat-contact-role">{c.job_title || c.role}</div>
                  </div>
                  {thread?.unread_count > 0 && <span className="chat-unread-dot" aria-label="Unread messages" />}
                </div>
              );
            })}
          </div>
        </div>

        {selectedGroupId && (
          <div className="chat-channels">
            <div className="chat-sidebar-heading">Channels</div>
            {channels.map((c) => (
              <div key={c.id}
                className={`chat-contact-item${activeConversation?.kind === 'channel' && activeConversation.id === c.id ? ' active' : ''}`}
                onClick={() => openChannel(c)}>
                <div className="chat-contact-name"># {c.name}</div>
                {isManagerOfGroup(groups.find((g) => g.id === selectedGroupId)) && channels.length > 1 && (
                  <button className="chat-delete-btn" title="Delete channel"
                    onClick={(e) => handleDeleteChannel(e, c.id)}>🗑</button>
                )}
              </div>
            ))}
            <form className="chat-new-channel-form" onSubmit={handleCreateChannel}>
              <input className="field-input" placeholder="+ new channel" value={newChannelName}
                onChange={(e) => setNewChannelName(e.target.value)} />
            </form>
          </div>
        )}

        <div className="chat-thread">
          {!activeConversation ? (
            <div className="chat-empty-state">Select a channel or someone to start messaging.</div>
          ) : (
            <>
              <div className="chat-thread-header">
                {activeConversation.kind === 'dm' ? activeConversation.otherUserName : `# ${activeConversation.channelName}`}
              </div>
              <div className="chat-messages">
                {messages.map((m) => (
                  <div key={m.id} className={`chat-bubble ${m.sender_user_id === myUserId ? 'sent' : 'received'}`}>
                    {activeConversation.kind === 'channel' && m.sender_user_id !== myUserId && (
                      <div className="chat-bubble-sender">{m.sender_name}</div>
                    )}
                    {m.body}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
              <form className="chat-composer" onSubmit={handleSend}>
                <input
                  className="field-input"
                  placeholder="Type a message…"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                />
                <button type="submit" className="btn-primary">Send</button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
