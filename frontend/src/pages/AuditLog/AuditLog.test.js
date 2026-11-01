import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';

import AuditLog from './AuditLog';
import * as auditApi from '../../api/auditApi';

jest.mock('../../api/auditApi', () => ({ listAuditLogs: jest.fn() }));

const ROW = {
  id: 40, occurred_at: '2026-11-01T10:00:00Z', actor_user_id: 2, actor_name: 'Hana HR', actor_role: 'hr_manager',
  action: 'leave_request.approved', entity_type: 'leave_request', entity_id: '9',
  before: { status: 'pending' }, after: { status: 'approved' }, correlation_id: 'abcdef1234567890',
};

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  auditApi.listAuditLogs.mockResolvedValue({ items: [ROW], next_before_id: 40 });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

const buttonByText = (text) => Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes(text));

test('renders who / what / before → after and pages older entries', async () => {
  await act(async () => root.render(<AuditLog />));
  expect(container.textContent).toContain('Hana HR');
  expect(container.textContent).toContain('leave_request.approved');
  expect(container.querySelector('.audit-before').textContent).toBe('pending');
  expect(container.querySelector('.audit-after').textContent).toBe('approved');

  await act(async () => buttonByText('Load older entries').click());
  expect(auditApi.listAuditLogs).toHaveBeenLastCalledWith(expect.objectContaining({ beforeId: 40 }));
});

test('filters are applied on submit and correlation ids drill down', async () => {
  await act(async () => root.render(<AuditLog />));
  await act(async () => Simulate.change(container.querySelector('#au-type'), { target: { value: 'project' } }));
  await act(async () => Simulate.submit(container.querySelector('form[aria-label="Filter audit log"]')));
  expect(auditApi.listAuditLogs).toHaveBeenLastCalledWith(expect.objectContaining({ entityType: 'project' }));

  await act(async () => container.querySelector('.audit-corr').click());
  expect(auditApi.listAuditLogs).toHaveBeenLastCalledWith(
    expect.objectContaining({ correlationId: 'abcdef1234567890', entityType: '' }),
  );
});

test('shows the API error (e.g. 403 for non-admins) instead of data', async () => {
  auditApi.listAuditLogs.mockRejectedValue({ response: { data: { detail: 'Insufficient permissions.' } } });
  await act(async () => root.render(<AuditLog />));
  expect(container.textContent).toContain('Insufficient permissions.');
  expect(container.querySelector('.audit-table')).toBeNull();
});
