import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

import Login from './Login';
import Register from './Register';
import * as authApi from '../../api/authApi';

jest.mock('../../api/authApi', () => ({
  getRegistrationStatus: jest.fn(),
  loginUser: jest.fn(),
  getCurrentUser: jest.fn(),
  registerUser: jest.fn(),
}));

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  jest.clearAllMocks();
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render(element) {
  await act(async () => {
    root.render(element);
  });
}

test('Login shows registration link when getRegistrationStatus is true', async () => {
  authApi.getRegistrationStatus.mockResolvedValue(true);

  await render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );

  // Wait a tick for useEffect
  await act(async () => {});

  const link = container.querySelector('a[href="/register"]');
  expect(link).not.toBeNull();
  expect(link.textContent).toBe('Create one');
  expect(container.textContent).not.toContain('Ask HR or an administrator');
});

test('Login hides registration link and shows HR guidance when getRegistrationStatus is false', async () => {
  authApi.getRegistrationStatus.mockResolvedValue(false);

  await render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );

  await act(async () => {});

  const link = container.querySelector('a[href="/register"]');
  expect(link).toBeNull();
  expect(container.textContent).toContain('Need an account? Ask HR or an administrator to create one for you.');
});

test('Register shows form when registration is open', async () => {
  authApi.getRegistrationStatus.mockResolvedValue(true);

  await render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>
  );

  await act(async () => {});

  expect(container.querySelector('form.login-form')).not.toBeNull();
  expect(container.querySelector('input#fullName')).not.toBeNull();
  expect(container.textContent).not.toContain('Self-registration is turned off');
});

test('Register hides form and displays notice when registration is closed', async () => {
  authApi.getRegistrationStatus.mockResolvedValue(false);

  await render(
    <MemoryRouter>
      <Register />
    </MemoryRouter>
  );

  await act(async () => {});

  expect(container.querySelector('form.login-form')).toBeNull();
  expect(container.textContent).toContain('Self-registration is turned off. Accounts are created by HR or an administrator');
});

