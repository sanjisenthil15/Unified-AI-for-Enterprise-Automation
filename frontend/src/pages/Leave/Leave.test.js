import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { MemoryRouter } from 'react-router-dom';

import Leave, { countWorkingDays } from './Leave';
import * as leaveApi from '../../api/leaveApi';

jest.mock('../../api/leaveApi', () => ({
  approveLeaveRequest: jest.fn(),
  cancelLeaveRequest: jest.fn(),
  getLeaveTypes: jest.fn(),
  getMyLeaveRequests: jest.fn(),
  listLeaveRequests: jest.fn(),
  rejectLeaveRequest: jest.fn(),
  submitLeaveRequest: jest.fn(),
}));

const employeeInfo = (name, email) => ({ id: 3, employee_code: 'EMP-3', job_title: 'Engineer', full_name: name, email });

const PENDING = {
  id: 11, employee: employeeInfo('Eve Engineer', 'eve@x.io'), leave_type: 'annual',
  start_date: '2026-12-07', end_date: '2026-12-09', working_days: 3, reason: 'Family trip',
  status: 'pending', reviewed_by: null, decision_note: null, created_at: '2026-11-01T10:00:00Z',
};

let container;
let root;

function signIn(role, email = 'me@x.io') {
  localStorage.setItem('user', JSON.stringify({ id: 1, email, full_name: 'Me', role: { name: role } }));
}

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  leaveApi.getLeaveTypes.mockResolvedValue({ leave_types: ['annual', 'sick', 'casual', 'unpaid', 'other'], max_span_days: 366 });
  leaveApi.getMyLeaveRequests.mockResolvedValue([]);
  leaveApi.listLeaveRequests.mockResolvedValue([PENDING]);
  leaveApi.submitLeaveRequest.mockResolvedValue({});
  leaveApi.approveLeaveRequest.mockResolvedValue({});
  leaveApi.rejectLeaveRequest.mockResolvedValue({});
  leaveApi.cancelLeaveRequest.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render() {
  await act(async () => root.render(<MemoryRouter><Leave /></MemoryRouter>));
}

const buttonByText = (text) => Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes(text));
async function change(el, value) {
  await act(async () => Simulate.change(el, { target: { value } }));
}

test('working-day count skips weekends and rejects reversed ranges', () => {
  expect(countWorkingDays('2026-12-07', '2026-12-13')).toBe(5); // Mon..Sun
  expect(countWorkingDays('2026-12-12', '2026-12-13')).toBe(0); // Sat..Sun
  expect(countWorkingDays('2026-12-09', '2026-12-07')).toBe(0);
});

test('employee submits a request and never sees approval controls', async () => {
  signIn('employee');
  await render();
  expect(leaveApi.listLeaveRequests).not.toHaveBeenCalled();
  expect(buttonByText('Approval queue')).toBeFalsy();

  await change(container.querySelector('#lv-type'), 'sick');
  await change(container.querySelector('#lv-start'), '2026-12-07');
  await change(container.querySelector('#lv-end'), '2026-12-09');
  await change(container.querySelector('#lv-reason'), 'Flu');
  expect(container.textContent).toContain('3 working days');
  await act(async () => Simulate.submit(container.querySelector('form[aria-label="Request leave"]')));
  expect(leaveApi.submitLeaveRequest).toHaveBeenCalledWith({
    leaveType: 'sick', startDate: '2026-12-07', endDate: '2026-12-09', reason: 'Flu',
  });
  expect(container.textContent).toContain('Leave request submitted');
});

test('reversed dates block submission client-side', async () => {
  signIn('employee');
  await render();
  await change(container.querySelector('#lv-start'), '2026-12-09');
  await change(container.querySelector('#lv-end'), '2026-12-07');
  expect(container.textContent).toContain('end date must be on or after');
  expect(container.querySelector('button[type="submit"]').disabled).toBe(true);
});

test('employee can cancel only pending requests', async () => {
  signIn('employee');
  leaveApi.getMyLeaveRequests.mockResolvedValue([
    PENDING,
    { ...PENDING, id: 12, status: 'approved', reviewed_by: { id: 9, full_name: 'Hana HR' } },
  ]);
  await render();
  const cancelButtons = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent === 'Cancel request');
  expect(cancelButtons).toHaveLength(1);
  await act(async () => cancelButtons[0].click());
  expect(leaveApi.cancelLeaveRequest).toHaveBeenCalledWith(11);
  expect(container.textContent).toContain('Approved by Hana HR');
});

test('HR approves from the queue; rejecting requires a reason', async () => {
  signIn('hr_manager');
  await render();
  await act(async () => buttonByText('Approval queue').click());
  expect(container.textContent).toContain('Eve Engineer');

  await act(async () => buttonByText('Approve').click());
  expect(leaveApi.approveLeaveRequest).toHaveBeenCalledWith(11, undefined); // no note typed

  await act(async () => buttonByText('Reject…').click());
  await act(async () => Simulate.submit(container.querySelector('.leave-reject-form')));
  expect(leaveApi.rejectLeaveRequest).not.toHaveBeenCalled();
  expect(container.textContent).toContain('A rejection reason is required');

  await change(container.querySelector('input[aria-label="Rejection reason"]'), 'Release week');
  await act(async () => Simulate.submit(container.querySelector('.leave-reject-form')));
  expect(leaveApi.rejectLeaveRequest).toHaveBeenCalledWith(11, 'Release week');
});

test('an approver sees no decision buttons on their own request', async () => {
  signIn('hr_manager', 'eve@x.io');
  await render();
  await act(async () => buttonByText('Approval queue').click());
  expect(buttonByText('Approve')).toBeFalsy();
  expect(container.textContent).toContain('another approver must decide it');
});

test('managers get no approval queue', async () => {
  signIn('manager');
  await render();
  expect(buttonByText('Approval queue')).toBeFalsy();
  expect(leaveApi.listLeaveRequests).not.toHaveBeenCalled();
});
