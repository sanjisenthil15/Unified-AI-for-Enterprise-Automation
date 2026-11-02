import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

import Projects from './Projects';
import * as employeeApi from '../../api/employeeApi';
import { allowedNextStatuses, canEditProjectMetadata, canManageProject } from '../../utils/projectLifecycle';

jest.mock('../../api/employeeApi', () => ({
  assignProjectManager: jest.fn(),
  assignTeamLead: jest.fn(),
  createProject: jest.fn(),
  deleteProject: jest.fn(),
  listEmployees: jest.fn(),
  listProjectMembers: jest.fn(),
  listProjects: jest.fn(),
  updateProject: jest.fn(),
  updateProjectStatus: jest.fn(),
}));

const PROJECTS = [
  {
    id: 1, name: 'Apollo', description: 'Payments revamp', status: 'active',
    start_date: '2026-10-01', deadline: '2026-12-31', member_count: 2,
    manager: { id: 50, full_name: 'Mona Manager', email: 'mona@x.io', is_active: true },
    team_lead: null, created_at: '2026-10-01T00:00:00Z',
  },
  {
    id: 2, name: 'Zephyr', description: null, status: 'archived',
    start_date: null, deadline: null, member_count: 0, manager: null, team_lead: null,
    created_at: '2026-09-01T00:00:00Z', archived_at: '2026-10-15T00:00:00Z',
  },
];

const EMPLOYEES = [
  { id: 7, job_title: 'Backend Developer', status: 'active', project: { id: 1, name: 'Apollo' },
    user: { id: 70, full_name: 'Eve Engineer', email: 'eve@x.io', is_active: true, role: { name: 'employee' } } },
  { id: 8, job_title: 'Engineering Manager', status: 'active', project: null,
    user: { id: 50, full_name: 'Mona Manager', email: 'mona@x.io', is_active: true, role: { name: 'manager' } } },
];

let container;
let root;

function signIn(role, id = 1) {
  localStorage.setItem('user', JSON.stringify({ id, full_name: 'Test', role: { name: role } }));
}

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  employeeApi.listProjects.mockResolvedValue(PROJECTS);
  employeeApi.listEmployees.mockResolvedValue(EMPLOYEES);
  employeeApi.listProjectMembers.mockResolvedValue([
    {
      id: 7,
      user_id: 70,
      full_name: 'Eve Engineer',
      email: 'eve@x.io',
      job_title: 'Backend Developer',
      role: 'employee',
      team_role: 'Member',
      department_name: 'Engineering',
      status: 'active',
    },
  ]);
  employeeApi.updateProjectStatus.mockResolvedValue({});
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render() {
  await act(async () => root.render(<MemoryRouter><Projects /></MemoryRouter>));
}

const buttons = () => Array.from(container.querySelectorAll('button'));
const buttonByText = (text) => buttons().find((b) => b.textContent.includes(text));

async function openCard(name) {
  const card = Array.from(container.querySelectorAll('.project-card')).find((c) => c.textContent.includes(name));
  await act(async () => card.click());
}

// ------------------------------------------------------------ lifecycle rules

test('lifecycle helpers mirror backend transitions and manage permissions', () => {
  expect(allowedNextStatuses('active')).toEqual(['on_hold', 'completed', 'cancelled', 'archived']);
  expect(allowedNextStatuses('archived')).toEqual([]);
  expect(allowedNextStatuses(undefined)).toEqual(['active', 'cancelled', 'archived']);
  const project = { status: 'active', manager: { id: 50 } };
  expect(canManageProject('hr_manager', 1, project)).toBe(true);
  expect(canManageProject('manager', 50, project)).toBe(true);
  expect(canManageProject('manager', 51, project)).toBe(false);
  expect(canManageProject('employee', 50, project)).toBe(false);
  expect(canEditProjectMetadata('admin', 1, { status: 'completed' })).toBe(false);
});

// ------------------------------------------------------------ page

test('admin sees create, assignment, lifecycle and delete controls', async () => {
  signIn('admin');
  await render();
  expect(buttonByText('+ New project')).toBeTruthy();
  expect(container.textContent).toContain('Apollo');
  expect(container.textContent).toContain('Zephyr');

  await openCard('Apollo');
  expect(buttonByText('Edit details')).toBeTruthy();
  expect(buttonByText('Move to on hold')).toBeTruthy();
  expect(buttonByText('Assign manager')).toBeTruthy();
  expect(buttonByText('Delete project')).toBeTruthy();
  // Only Manager-role accounts are offered as project managers.
  const managerOptions = Array.from(container.querySelector('select[aria-label="Choose project manager"]').options)
    .map((o) => o.textContent);
  expect(managerOptions).toContain('Mona Manager');
  expect(managerOptions).not.toContain('Eve Engineer');
});

test('a lifecycle button calls the status API and reloads', async () => {
  signIn('admin');
  await render();
  await openCard('Apollo');
  await act(async () => buttonByText('Move to on hold').click());
  expect(employeeApi.updateProjectStatus).toHaveBeenCalledWith(1, 'on_hold');
  expect(employeeApi.listProjects).toHaveBeenCalledTimes(2);
});

test('archived projects offer no edit or lifecycle actions', async () => {
  signIn('admin');
  await render();
  await openCard('Zephyr');
  expect(buttonByText('Edit details')).toBeFalsy();
  expect(buttons().some((b) => b.textContent.startsWith('Move to'))).toBe(false);
});

test('assigned manager can run the lifecycle but not staff or delete', async () => {
  signIn('manager', 50);
  await render();
  expect(buttonByText('+ New project')).toBeFalsy();
  await openCard('Apollo');
  expect(buttonByText('Edit details')).toBeTruthy();
  expect(buttonByText('Move to on hold')).toBeTruthy();
  expect(buttonByText('Assign manager')).toBeFalsy();
  expect(buttonByText('Delete project')).toBeFalsy();
});

test('employee view is read-only and never calls the employee directory', async () => {
  signIn('employee', 70);
  await render();
  expect(employeeApi.listEmployees).not.toHaveBeenCalled();
  expect(buttonByText('+ New project')).toBeFalsy();
  await openCard('Apollo');
  expect(buttonByText('Edit details')).toBeFalsy();
  expect(buttons().some((b) => b.textContent.startsWith('Move to'))).toBe(false);
  expect(employeeApi.listProjectMembers).toHaveBeenCalledWith(1);
  expect(container.textContent).toContain('Eve Engineer');
  expect(container.textContent).toContain('Backend Developer');
  expect(container.textContent).toContain('2 members on this project.');
});

test('status filter narrows the list', async () => {
  signIn('admin');
  await render();
  await act(async () => buttonByText('archived (1)').click());
  const names = Array.from(container.querySelectorAll('.project-card-name')).map((n) => n.textContent);
  expect(names).toEqual(['Zephyr']);
});

test('team lead is shown in leadership section but not duplicated in members list', async () => {
  const projectWithLead = [
    {
      id: 3,
      name: 'Titan',
      description: 'Core infra',
      status: 'active',
      start_date: '2026-10-01',
      deadline: '2026-12-31',
      member_count: 2,
      manager: { id: 50, full_name: 'Elena Rostova', email: 'elena.rostova@employee.demo' },
      team_lead: {
        id: 30,
        job_title: 'Team Lead',
        user: { id: 300, full_name: 'Vishwa G', email: 'vishwa@employee.demo' },
      },
      created_at: '2026-10-01T00:00:00Z',
    },
  ];

  employeeApi.listProjects.mockResolvedValue(projectWithLead);
  employeeApi.listProjectMembers.mockResolvedValue([
    {
      id: 30,
      user_id: 300,
      full_name: 'Vishwa G',
      email: 'vishwa@employee.demo',
      job_title: 'Team Lead',
      role: 'employee',
      team_role: 'Team Lead',
      department_name: 'Engineering',
      status: 'active',
    },
    {
      id: 31,
      user_id: 301,
      full_name: 'Chloe Bennett',
      email: 'chloe@employee.demo',
      job_title: 'Frontend Developer',
      role: 'employee',
      team_role: 'Member',
      department_name: 'Engineering',
      status: 'active',
    },
  ]);

  signIn('employee', 300);
  await render();
  await openCard('Titan');

  // Vishwa G should appear in leadership card
  expect(container.textContent).toContain('Vishwa G');
  expect(container.textContent).toContain('Chloe Bennett');

  // Verify that inside the project-members list, Vishwa G is NOT duplicated
  const memberListItems = Array.from(container.querySelectorAll('.project-member-item'));
  const memberNames = memberListItems.map((li) => li.querySelector('strong')?.textContent);
  expect(memberNames).toEqual(['Chloe Bennett']);
  expect(memberNames).not.toContain('Vishwa G');
});

