/**
 * pages/Chat/Chat.js
 *
 * 1:1 chat between an employee and their manager (project team lead, or
 * admin/hr_manager) — see core/authorization.py's can_open_chat for the
 * exact rule. Polling-based, same idiom as pages/Meetings/Meetings.js.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  getContacts, getMessages, listThreads, markThreadRead, openThread, sendMessage,
} from '../../api/chatApi';
import '../Recruitment/Recruitment.css';
import '../HRDashboard/HRDashboard.css';
import './Chat.css';

const THREAD_LIST_POLL_MS = 15000;
const MESSAGE_POLL_MS = 4000;

function currentUserId() {
  try {
    return JSON.parse(localStorage.getItem('user'))?.id ?? null;
  } catch {
    return null;
  }
}

export default function Chat() {
  const [searchParams, setSearchParams] = useSearchParams();
  const myUserId = currentUserId();

  const [contacts, setContacts] = useState([]);
  const [threads, setThreads] = useState([]);
  const [activeThread, setActiveThread] = useState(null); // { id, other_user_id, other_user_name }
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const lastMessageIdRef = useRef(null);
  const messagesEndRef = useRef(null);

  const loadContactsAndThreads = useCallback(async () => {
    try {
      const [contactList, threadList] = await Promise.all([getContacts(), listThreads()]);
      setContacts(contactList);
      setThreads(threadList);
    } catch {
      setError('Could not load your contacts.');
    }
  }, []);

  useEffect(() => {
    loadContactsAndThreads();
    const t = setInterval(loadContactsAndThreads, THREAD_LIST_POLL_MS);
    return () => clearInterval(t);
  }, [loadContactsAndThreads]);

  const openWithUser = useCallback(async (otherUserId) => {
    try {
      const thread = await openThread(otherUserId);
      setActiveThread(thread);
      setMessages([]);
      lastMessageIdRef.current = null;
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not open this conversation.');
    }
  }, []);

  // Deep-link support: /chat?with={userId} (used by Sprints' Team Review "Message" button).
  // Intentionally runs once on mount only — openWithUser is a stable
  // useCallback, and re-running on every searchParams change (which this
  // effect itself triggers via setSearchParams) would loop.
  useEffect(() => {
    const withUserId = searchParams.get('with');
    if (withUserId) {
      openWithUser(Number(withUserId));
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line
  }, []);

  const pollMessages = useCallback(async () => {
    if (!activeThread) return;
    try {
      const newMessages = await getMessages(activeThread.id, lastMessageIdRef.current);
      if (newMessages.length) {
        setMessages((prev) => [...prev, ...newMessages]);
        lastMessageIdRef.current = newMessages[newMessages.length - 1].id;
        markThreadRead(activeThread.id).catch(() => {});
      }
    } catch {
      // transient — next poll will retry
    }
  }, [activeThread]);

  useEffect(() => {
    if (!activeThread) return undefined;
    pollMessages();
    const t = setInterval(pollMessages, MESSAGE_POLL_MS);
    return () => clearInterval(t);
  }, [activeThread, pollMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    if (!draft.trim() || !activeThread) return;
    try {
      const msg = await sendMessage(activeThread.id, draft.trim());
      setMessages((prev) => [...prev, msg]);
      lastMessageIdRef.current = msg.id;
      setDraft('');
      loadContactsAndThreads();
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
        <div><h1>Team Chat</h1><p>Message your team lead, your project's members, or HR/admin directly.</p></div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="chat-layout">
        <div className="chat-contacts">
          {contacts.length === 0 && (
            <p style={{ padding: '1rem', color: 'var(--text-muted)' }}>No contacts yet.</p>
          )}
          {contacts.map((c) => {
            const thread = threadForContact(c.user_id);
            return (
              <div
                key={c.user_id}
                className={`chat-contact-item${activeThread?.other_user_id === c.user_id ? ' active' : ''}`}
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

        <div className="chat-thread">
          {!activeThread ? (
            <div className="chat-empty-state">Select someone to start messaging.</div>
          ) : (
            <>
              <div className="chat-thread-header">{activeThread.other_user_name}</div>
              <div className="chat-messages">
                {messages.map((m) => (
                  <div key={m.id} className={`chat-bubble ${m.sender_user_id === myUserId ? 'sent' : 'received'}`}>
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
