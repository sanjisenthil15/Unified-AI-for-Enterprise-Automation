import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

import Notifications from './Notifications';
import * as api from '../../api/notificationsApi';

jest.mock('../../api/notificationsApi', () => ({
  getMyNotifications: jest.fn(),
  getUnreadCount: jest.fn(),
  listEscalations: jest.fn(),
  markAllNotificationsRead: jest.fn(),
  markNotificationRead: jest.fn(),
  runEscalationSweep: jest.fn(),
}));

const NOTES = [
  { id: 3, type: 'leave_approved', category: 'leave', message: 'Your leave was approved', link: '/leave', read_at: null, created_at: '2026-11-01T10:00:00Z' },
  { id: 2, type: 'task_assigned', category: 'sprint', message: 'You were assigned X', link: '/sprints', read_at: '2026-11-01T09:00:00Z', created_at: '2026-11-01T08:00:00Z' },
];

let container;
let root;

function signIn(role) {
  localStorage.setItem('user', JSON.stringify({ id: 1, role: { name: role } }));
}

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  api.getMyNotifications.mockResolvedValue(NOTES);
  api.getUnreadCount.mockResolvedValue({ total: 1, by_category: { leave: 1 } });
  api.listEscalations.mockResolvedValue([
    { id: 5, rule: 'leave_pending_overdue', entity_type: 'leave_request', entity_id: 9, status: 'open',
      summary: 'Leave request #9 pending over 48h', recipient_count: 2, triggered_at: '2026-11-01T10:00:00Z', resolved_at: null },
  ]);
  api.markAllNotificationsRead.mockResolvedValue({ updated: 1 });
  api.runEscalationSweep.mockResolvedValue({ skipped: false, opened: 0, resolved: 1 });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render() {
  await act(async () => root.render(<MemoryRouter><Notifications /></MemoryRouter>));
}

const buttonByText = (text) => Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes(text));

test('shows notifications with per-category unread counts and filters by category', async () => {
  signIn('employee');
  await render();
  expect(container.textContent).toContain('Your leave was approved');
  expect(container.querySelectorAll('.notif-row.unread')).toHaveLength(1);
  expect(buttonByText('Leave').textContent).toContain('1');

  await act(async () => buttonByText('Leave').click());
  expect(api.getMyNotifications).toHaveBeenLastCalledWith({ category: 'leave', unreadOnly: false, limit: 30 });

  await act(async () => buttonByText('Mark these read').click());
  expect(api.markAllNotificationsRead).toHaveBeenCalledWith({ category: 'leave' });
});

test('employees never see or load escalations', async () => {
  signIn('employee');
  await render();
  expect(api.listEscalations).not.toHaveBeenCalled();
  expect(container.textContent).not.toContain('Run check now');
});

test('HR sees escalations but cannot force a sweep; admin can', async () => {
  signIn('hr_manager');
  await render();
  expect(container.textContent).toContain('Leave request #9 pending over 48h');
  expect(buttonByText('Run check now')).toBeFalsy();

  await act(async () => root.unmount());
  root = createRoot(container);
  signIn('admin');
  await render();
  await act(async () => buttonByText('Run check now').click());
  expect(api.runEscalationSweep).toHaveBeenCalled();
  expect(container.textContent).toContain('1 resolved');
});
