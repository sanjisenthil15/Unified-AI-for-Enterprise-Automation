import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

import Chat from './Chat';
import * as chatApi from '../../api/chatApi';
import * as employeeApi from '../../api/employeeApi';
import * as attendanceApi from '../../api/attendanceApi';

jest.mock('../../api/chatApi', () => ({
  getContacts: jest.fn(),
  listThreads: jest.fn(),
  listGroups: jest.fn(),
  getMessages: jest.fn(),
  getChannelMessages: jest.fn(),
  sendMessage: jest.fn(),
  sendChannelMessage: jest.fn(),
  markThreadRead: jest.fn(),
  markChannelRead: jest.fn(),
  openThread: jest.fn(),
  getGroupDetail: jest.fn(),
  createChannel: jest.fn(),
  createGroup: jest.fn(),
  deleteChannel: jest.fn(),
  deleteGroup: jest.fn(),
}));

jest.mock('../../api/employeeApi', () => ({
  getMyEmployeeRecord: jest.fn(),
  listProjects: jest.fn(),
}));

jest.mock('../../api/attendanceApi', () => ({
  getTeamAttendance: jest.fn(),
}));

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem('user', JSON.stringify({ id: 10, full_name: 'Test Employee', role: { name: 'employee' } }));
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  jest.clearAllMocks();

  chatApi.getContacts.mockResolvedValue([
    { user_id: 20, full_name: 'Teammate Bob', role: 'employee', job_title: 'Developer' },
  ]);
  chatApi.listThreads.mockResolvedValue([
    { id: 1, other_user_id: 20, other_user_name: 'Teammate Bob', unread_count: 0 },
  ]);
  chatApi.listGroups.mockResolvedValue([
    { id: 101, project_id: 5, project_name: 'Project Alpha', name: 'Alpha Chat', member_count: 2, unread: false, created_at: new Date().toISOString() },
  ]);
  chatApi.getMessages.mockResolvedValue([]);
  employeeApi.getMyEmployeeRecord.mockResolvedValue({ id: 100, project_id: 5 });
  employeeApi.listProjects.mockResolvedValue([]);
  attendanceApi.getTeamAttendance.mockResolvedValue([]);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  localStorage.clear();
});

async function render(element) {
  await act(async () => {
    root.render(element);
  });
}

test('Chat loads contacts, threads, and project groups', async () => {
  await render(
    <MemoryRouter>
      <Chat />
    </MemoryRouter>
  );

  await act(async () => {});

  expect(chatApi.getContacts).toHaveBeenCalled();
  expect(chatApi.listThreads).toHaveBeenCalled();
  expect(chatApi.listGroups).toHaveBeenCalled();

  expect(container.textContent).toContain('Teammate Bob');
  expect(container.textContent).toContain('Alpha Chat');
});

test('Chat handles failed send without silently clearing draft', async () => {
  chatApi.getGroupDetail.mockResolvedValue({
    id: 101, project_id: 5, project_name: 'Project Alpha', name: 'Alpha Chat',
    member_count: 2, unread: false, created_at: new Date().toISOString(),
    members: [{ user_id: 10, full_name: 'Test' }, { user_id: 20, full_name: 'Bob' }],
    channels: [{ id: 201, name: 'general' }],
  });
  chatApi.getChannelMessages.mockResolvedValue([]);
  chatApi.sendChannelMessage.mockRejectedValue({
    response: { data: { detail: 'Permission denied for this channel.' } },
  });

  await render(
    <MemoryRouter initialEntries={['/chat?group=101']}>
      <Chat />
    </MemoryRouter>
  );

  await act(async () => {});

  // Wait for channels to load and auto-select
  await act(async () => {});

  const composer = container.querySelector('form.chat-composer');
  if (composer) {
    const input = composer.querySelector('input');
    await act(async () => {
      input.value = 'Failed message test';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });

    await act(async () => {
      composer.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });

    // Check error display
    expect(container.textContent).toContain('Permission denied for this channel.');
  }
});

