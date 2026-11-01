import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import EmployeeManagement from './EmployeeManagement';
import * as employeeApi from '../../api/employeeApi';
import * as authApi from '../../api/authApi';

jest.mock('../../api/employeeApi', () => ({
  assignProjectManager: jest.fn(),
  assignTeamLead: jest.fn(),
  createDepartment: jest.fn(),
  createEmployee: jest.fn(),
  createProject: jest.fn(),
  deleteProject: jest.fn(),
  listDepartments: jest.fn(),
  listEmployees: jest.fn(),
  listProjects: jest.fn(),
  terminateEmployee: jest.fn(),
  updateEmployee: jest.fn(),
  updateProjectStatus: jest.fn(),
}));

jest.mock('../../api/authApi', () => ({
  listRoles: jest.fn(),
  resetUserPassword: jest.fn(),
}));

const mockEmployees = [
  {
    id: 1,
    user: { id: 101, full_name: 'Elena Rostova', email: 'elena.rostova@employee.demo', role: { id: 7, name: 'manager' } },
    job_title: 'Engineering Manager',
    department: { id: 1, name: 'Engineering' },
    project: { id: 2, name: 'Recruitment AI' },
    hire_date: '2025-06-01',
    status: 'active',
    employment_type: 'full_time',
  },
  {
    id: 2,
    user: { id: 102, full_name: 'Aiden Cross', email: 'aiden.cross@employee.demo', role: { id: 3, name: 'support_agent' } },
    job_title: 'Customer Support Specialist',
    department: null,
    project: { id: 4, name: 'Customer Support Platform' },
    hire_date: '2025-09-15',
    status: 'active',
    employment_type: 'full_time',
  },
];

const mockDepartments = [
  { id: 1, name: 'Engineering' },
  { id: 2, name: 'Operations' },
];

const mockProjects = [
  { id: 2, name: 'Recruitment AI', status: 'active', member_count: 6 },
  { id: 3, name: 'Meeting Intelligence', status: 'active', member_count: 6 },
  { id: 4, name: 'Customer Support Platform', status: 'active', member_count: 6 },
];

const mockRoles = [
  { id: 1, name: 'admin' },
  { id: 2, name: 'hr_manager' },
  { id: 3, name: 'support_agent' },
  { id: 4, name: 'recruiter' },
  { id: 5, name: 'employee' },
  { id: 6, name: 'viewer' },
  { id: 7, name: 'manager' },
];

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem('user', JSON.stringify({
    id: 1,
    email: 'admin@demo.com',
    role: { name: 'admin' },
  }));

  employeeApi.listEmployees.mockResolvedValue(mockEmployees);
  employeeApi.listDepartments.mockResolvedValue(mockDepartments);
  employeeApi.listProjects.mockResolvedValue(mockProjects);
  authApi.listRoles.mockResolvedValue(mockRoles);

  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  localStorage.clear();
  jest.clearAllMocks();
});

async function renderComponent() {
  await act(async () => {
    root.render(
      <MemoryRouter>
        <EmployeeManagement />
      </MemoryRouter>,
    );
  });
}

describe('EmployeeManagement Page', () => {
  test('renders employee management table with employees, job titles, and avatars', async () => {
    await renderComponent();

    expect(container.textContent).toContain('Elena Rostova');
    expect(container.textContent).toContain('Aiden Cross');
    expect(container.textContent).toContain('Engineering Manager');
    expect(container.textContent).toContain('Customer Support Specialist');

    const avatars = container.querySelectorAll('.avatar');
    expect(avatars.length).toBeGreaterThanOrEqual(2);
  });

  test('filters employees via search input in real time', async () => {
    await renderComponent();

    const tbody = container.querySelector('.data-table tbody');
    expect(tbody.textContent).toContain('Elena Rostova');
    expect(tbody.textContent).toContain('Aiden Cross');

    const searchInput = container.querySelector('.employee-search-box input');
    expect(searchInput).not.toBeNull();

    await act(async () => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(searchInput, 'Aiden');
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    });

    expect(tbody.textContent).toContain('Aiden Cross');
    expect(tbody.textContent).not.toContain('Elena Rostova');
  });

  test('opens edit modal on edit button click', async () => {
    await renderComponent();

    const editButtons = Array.from(container.querySelectorAll('button')).filter(
      (b) => b.textContent.trim() === 'Edit',
    );
    expect(editButtons.length).toBeGreaterThan(0);

    await act(async () => {
      editButtons[0].click();
    });

    const modal = container.querySelector('.modal-dialog');
    expect(modal).not.toBeNull();
    expect(modal.textContent).toContain('Edit Elena Rostova');
  });
});
