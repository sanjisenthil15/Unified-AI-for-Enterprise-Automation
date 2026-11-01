import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import ChangePassword from './ChangePassword';
import ChangePasswordForm from './ChangePasswordForm';
import { apiErrorText, isPasswordValid, passwordRules, utf8ByteLength } from '../../utils/passwordPolicy';
import axiosInstance from '../../api/axiosInstance';
import * as authApi from '../../api/authApi';

jest.mock('../../api/authApi', () => ({
  changePassword: jest.fn(),
  getCurrentUser: jest.fn(),
}));

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render(element) {
  await act(async () => root.render(element));
}

async function type(selectorIndex, value) {
  const input = container.querySelectorAll('input')[selectorIndex];
  await act(async () => Simulate.change(input, { target: { value } }));
}

const submitButton = () => container.querySelector('button[type="submit"]');

// ------------------------------------------------------------------ policy

test('password policy mirrors the backend rules, including the 72-byte limit', () => {
  expect(isPasswordValid('BrandNew1Pass')).toBe(true);
  expect(isPasswordValid('short1A')).toBe(false);
  expect(isPasswordValid('nouppercase1')).toBe(false);
  expect(isPasswordValid('NoDigitsHere')).toBe(false);
  const multibyte = `A1${'é'.repeat(36)}`; // 38 chars, 74 bytes
  expect(utf8ByteLength(multibyte)).toBe(74);
  expect(utf8ByteLength('😀')).toBe(4); // astral code point
  expect(utf8ByteLength(`A1${'x'.repeat(70)}`)).toBe(72);
  expect(passwordRules(multibyte).find((r) => r.key === 'bytes').ok).toBe(false);
});

test('apiErrorText reads string, validation-list and coded details', () => {
  expect(apiErrorText({ response: { data: { detail: 'Current password is incorrect.' } } }, 'x'))
    .toBe('Current password is incorrect.');
  expect(apiErrorText({ response: { data: { detail: [{ msg: 'Value error, Passwords do not match.' }] } } }, 'x'))
    .toBe('Passwords do not match.');
  expect(apiErrorText({ response: { data: { detail: { code: 'c', message: 'Coded message' } } } }, 'x'))
    .toBe('Coded message');
  expect(apiErrorText({}, 'fallback')).toBe('fallback');
});

// -------------------------------------------------------------------- form

test('submit stays disabled until the new password is valid, different and confirmed', async () => {
  await render(<ChangePasswordForm />);
  expect(submitButton().disabled).toBe(true);
  await type(0, 'TempPass1');
  await type(1, 'weak');
  await type(2, 'weak');
  expect(submitButton().disabled).toBe(true);
  await type(1, 'BrandNew1Pass');
  await type(2, 'Mismatch1Pass');
  expect(container.textContent).toContain('Passwords do not match.');
  expect(submitButton().disabled).toBe(true);
  await type(2, 'BrandNew1Pass');
  expect(submitButton().disabled).toBe(false);
});

test('successful change stores the fresh token and refreshed user, then reports success', async () => {
  localStorage.setItem('access_token', 'old-token');
  authApi.changePassword.mockResolvedValue({ access_token: 'new-token', token_type: 'bearer' });
  authApi.getCurrentUser.mockResolvedValue({ id: 7, full_name: 'Ada', must_change_password: false, role: { name: 'employee' } });
  const onSuccess = jest.fn();

  await render(<ChangePasswordForm onSuccess={onSuccess} />);
  await type(0, 'TempPass1');
  await type(1, 'BrandNew1Pass');
  await type(2, 'BrandNew1Pass');
  await act(async () => Simulate.submit(container.querySelector('form')));

  expect(authApi.changePassword).toHaveBeenCalledWith({
    currentPassword: 'TempPass1', newPassword: 'BrandNew1Pass', confirmPassword: 'BrandNew1Pass',
  });
  expect(localStorage.getItem('access_token')).toBe('new-token');
  expect(JSON.parse(localStorage.getItem('user')).must_change_password).toBe(false);
  expect(onSuccess).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
});

test('server rejection is shown and the existing session is kept', async () => {
  localStorage.setItem('access_token', 'old-token');
  authApi.changePassword.mockRejectedValue({ response: { status: 400, data: { detail: 'Current password is incorrect.' } } });

  await render(<ChangePasswordForm />);
  await type(0, 'WrongPass1');
  await type(1, 'BrandNew1Pass');
  await type(2, 'BrandNew1Pass');
  await act(async () => Simulate.submit(container.querySelector('form')));

  expect(container.querySelector('[role="alert"]').textContent).toBe('Current password is incorrect.');
  expect(localStorage.getItem('access_token')).toBe('old-token');
});

// -------------------------------------------------------- mandatory page

let routerKey = 0;
function renderPageAt(path) {
  routerKey += 1; // fresh router each time: MemoryRouter only reads initialEntries on mount
  return render(
    <MemoryRouter key={routerKey} initialEntries={[path]}>
      <Routes>
        <Route path="/change-password" element={<ChangePassword />} />
        <Route path="/login" element={<p>login page</p>} />
        <Route path="/profile" element={<p>profile page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

test('mandatory page requires a session and only serves flagged accounts', async () => {
  await renderPageAt('/change-password');
  expect(container.textContent).toContain('login page');

  localStorage.setItem('access_token', 't');
  localStorage.setItem('user', JSON.stringify({ full_name: 'Ada Lovelace', must_change_password: false }));
  await renderPageAt('/change-password');
  expect(container.textContent).toContain('profile page');

  localStorage.setItem('user', JSON.stringify({ full_name: 'Ada Lovelace', must_change_password: true }));
  await renderPageAt('/change-password');
  expect(container.textContent).toContain('Set your new password');
  expect(container.textContent).toContain('Temporary password');
  expect(container.textContent).toContain('Not you? Sign out');
});

// ------------------------------------------------------ session handling

describe('shared axios session handling', () => {
  const realLocation = window.location;
  const rejected = axiosInstance.interceptors.response.handlers[0].rejected;

  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true, writable: true,
      value: { pathname: '/dashboard', assign: jest.fn() },
    });
    localStorage.setItem('access_token', 't');
    localStorage.setItem('user', JSON.stringify({ id: 1, must_change_password: false }));
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, writable: true, value: realLocation });
  });

  const fail = (status, url, detail) => rejected({ config: { url }, response: { status, data: { detail } } }).catch((e) => e);

  test('401 on an app request clears the session and goes to /login', async () => {
    await fail(401, '/api/v1/sprints');
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(window.location.assign).toHaveBeenCalledWith('/login');
  });

  test('401 from the login form itself does not redirect or clear anything', async () => {
    await fail(401, '/api/v1/auth/login');
    expect(window.location.assign).not.toHaveBeenCalled();
    expect(localStorage.getItem('access_token')).toBe('t');
  });

  test('password_change_required 403 routes to the mandatory screen', async () => {
    await fail(403, '/api/v1/sprints', { code: 'password_change_required', message: 'x' });
    expect(window.location.assign).toHaveBeenCalledWith('/change-password');
    expect(JSON.parse(localStorage.getItem('user')).must_change_password).toBe(true);
  });

  test('ordinary permission 403 is left to the page', async () => {
    await fail(403, '/api/v1/analytics/overview', 'Access denied.');
    expect(window.location.assign).not.toHaveBeenCalled();
    expect(localStorage.getItem('access_token')).toBe('t');
  });

  test('no redirect loop when already on /login', async () => {
    window.location.pathname = '/login';
    await fail(401, '/api/v1/auth/me');
    expect(window.location.assign).not.toHaveBeenCalled();
  });
});
