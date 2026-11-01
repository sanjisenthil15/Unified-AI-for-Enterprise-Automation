import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import IncidentManagement from './IncidentManagement';
import * as incidentApi from '../../api/incidentApi';

jest.mock('../../api/incidentApi', () => ({
  getIncidentStats: jest.fn(),
  listIncidents: jest.fn(),
  getIncident: jest.fn(),
  createIncident: jest.fn(),
  updateIncident: jest.fn(),
  deleteIncident: jest.fn(),
  updateIncidentStatus: jest.fn(),
  assignIncident: jest.fn(),
  resolveIncident: jest.fn(),
  closeIncident: jest.fn(),
  runAITriage: jest.fn(),
  getLatestTriage: jest.fn(),
  getTimeline: jest.fn(),
  listIncidentTeams: jest.fn(),
  listTeamMembers: jest.fn(),
}));

const mockIncident = {
  id: 1,
  title: 'Database connection pool timeout',
  description: 'Postgres connection pool exhausted under high peak load during batch indexing.',
  severity: 'high',
  status: 'open',
  affected_system: 'Core Database',
  reported_by: 10,
  assigned_to: 11,
  reporter: { id: 10, full_name: 'Test Reporter' },
  assignee: { id: 11, full_name: 'Elena Rostova' },
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:05:00Z',
  resolved_at: null,
  root_cause: null,
};


const mockTeams = [
  {
    id: 'proj_4',
    team_id: 4,
    team_type: 'project',
    name: 'Customer Support Platform',
    member_count: 2,
    members: [
      { user_id: 222, employee_id: 42, full_name: 'Sarathi', email: 'sarathi@employee.demo', job_title: 'Software Developer', role: 'employee', status: 'active' },
      { user_id: 16288, employee_id: 5615, full_name: 'Aiden Cross', email: 'aiden.cross@employee.demo', job_title: 'Support Specialist', role: 'support_agent', status: 'active' },
    ],
  },
  {
    id: 'proj_2',
    team_id: 2,
    team_type: 'project',
    name: 'Recruitment AI',
    member_count: 1,
    members: [
      { user_id: 211, employee_id: 31, full_name: 'Sanjith', email: 'sanjith@employee.demo', job_title: 'Developer', role: 'employee', status: 'active' },
    ],
  },
];

const mockTriageResult = {
  id: 1,
  incident_id: 1,
  suggested_severity: 'critical',
  suggested_owner: 'Database Reliability Team',
  confidence: 94.5,
  ai_model: 'gemini-3.6-flash',
  reasoning: 'Connection pool saturation directly impacts user availability and leads to cascading timeouts across downstream services.',
  generated_at: '2026-11-01T10:06:00Z',
};

describe('IncidentManagement AI Triage', () => {
  let container;
  let root;

  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);

    localStorage.clear();
    incidentApi.getIncidentStats.mockResolvedValue({
      total: 1, open: 1, investigating: 0, resolved: 0, closed: 0,
      sev_low: 0, sev_medium: 0, sev_high: 1, sev_critical: 0,
      avg_resolution_time_minutes: null,
    });
    incidentApi.listIncidents.mockResolvedValue([mockIncident]);
    incidentApi.getIncident.mockResolvedValue(mockIncident);
    incidentApi.getLatestTriage.mockRejectedValue(new Error('No triage yet'));
    incidentApi.runAITriage.mockResolvedValue(mockTriageResult);
    incidentApi.listIncidentTeams.mockResolvedValue(mockTeams);
    incidentApi.listTeamMembers.mockImplementation(teamId => {
      const match = mockTeams.find(t => t.id === teamId);
      return Promise.resolve(match ? match.members : []);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    jest.clearAllMocks();
  });

  test('displays visible Run AI Triage button for admin in AI Triage section', async () => {
    localStorage.setItem('user', JSON.stringify({
      id: 1,
      full_name: 'Admin User',
      email: 'admin@demo.com',
      role: { id: 1, name: 'admin' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 50));
    });

    // Select the incident
    const row = container.querySelector('.clickable-row');
    expect(row).toBeTruthy();

    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    // Verify AI Triage section is present
    const triageSection = container.querySelector('.inc-triage-section');
    expect(triageSection).toBeTruthy();

    // Verify Run AI Triage button exists
    const runButtons = triageSection.querySelectorAll('button');
    const hasRunBtn = Array.from(runButtons).some(b => b.textContent.includes('Run AI Triage'));
    expect(hasRunBtn).toBe(true);

    // Verify empty state text
    expect(triageSection.textContent).toContain('No AI triage yet');
  });

  test('clicking Run AI Triage executes Gemini triage, shows loading state, and displays analysis', async () => {
    localStorage.setItem('user', JSON.stringify({
      id: 1,
      full_name: 'Admin User',
      email: 'admin@demo.com',
      role: { id: 1, name: 'admin' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 50));
    });

    // Select incident
    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const triageSection = container.querySelector('.inc-triage-section');
    const runBtn = Array.from(triageSection.querySelectorAll('button')).find(b => b.textContent.includes('Run AI Triage'));
    expect(runBtn).toBeTruthy();

    // Click Run AI Triage
    await act(async () => {
      runBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(incidentApi.runAITriage).toHaveBeenCalledWith(1);
    expect(incidentApi.getIncident).toHaveBeenCalledWith(1);

    // Verify AI analysis is now displayed
    expect(triageSection.textContent).toContain('Database Reliability Team');
    expect(triageSection.textContent).toContain('94.5%');
    expect(triageSection.textContent).toContain('Connection pool saturation');
    expect(triageSection.textContent).toContain('gemini-3.6-flash');

    // Verify re-triage button is available
    const rerunBtn = Array.from(triageSection.querySelectorAll('button')).find(b => b.textContent.includes('Run AI Triage Again'));
    expect(rerunBtn).toBeTruthy();
  });

  test('shows informative error message when AI Triage API fails', async () => {
    incidentApi.runAITriage.mockRejectedValueOnce({
      response: { data: { detail: 'Gemini service quota exceeded. Please retry shortly.' } },
    });

    localStorage.setItem('user', JSON.stringify({
      id: 2,
      full_name: 'Elena Rostova',
      role: { id: 7, name: 'manager' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 50));
    });

    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const triageSection = container.querySelector('.inc-triage-section');
    const runBtn = Array.from(triageSection.querySelectorAll('button')).find(b => b.textContent.includes('Run AI Triage'));

    await act(async () => {
      runBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    // Error alert is rendered
    expect(triageSection.textContent).toContain('Gemini service quota exceeded');
  });

  test('non-authorized roles see read-only information without action button', async () => {
    localStorage.setItem('user', JSON.stringify({
      id: 5,
      full_name: 'Employee User',
      role: { id: 2, name: 'employee' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 50));
    });

    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const triageSection = container.querySelector('.inc-triage-section');
    expect(triageSection).toBeTruthy();

    // No run button rendered for employee
    const runButtons = Array.from(triageSection.querySelectorAll('button')).filter(b => b.textContent.includes('Run AI Triage'));
    expect(runButtons.length).toBe(0);

    // Informative message displayed
    expect(triageSection.textContent).toContain('No AI triage yet');
  });

  test('preselects AI-recommended team in assign modal when matching team exists', async () => {
    incidentApi.getLatestTriage.mockResolvedValueOnce({
      id: 1,
      incident_id: 1,
      suggested_owner: 'Customer Support Platform',
      suggested_severity: 'high',
    });

    localStorage.setItem('user', JSON.stringify({
      id: 2,
      full_name: 'Elena Rostova',
      role: { id: 7, name: 'manager' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    // Open Assign Modal
    const assignBtn = Array.from(container.querySelectorAll('.inc-action-bar button')).find(b => b.textContent === 'Assign');
    expect(assignBtn).toBeTruthy();

    await act(async () => {
      assignBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    // Verify modal opened
    const modal = container.querySelector('.modal-overlay');
    expect(modal).toBeTruthy();
    expect(modal.textContent).toContain('Assign Incident');

    // Verify AI recommendation banner is shown with Preselected badge
    const matchedBanner = modal.querySelector('[data-testid="ai-rec-matched"]');
    expect(matchedBanner).toBeTruthy();
    expect(matchedBanner.textContent).toContain('Customer Support Platform');
    expect(matchedBanner.textContent).toContain('Preselected');

    // Verify Team select has Customer Support Platform selected
    const teamSelect = modal.querySelector('#inc-assign-team');
    expect(teamSelect).toBeTruthy();
    expect(teamSelect.value).toBe('proj_4');

    // Verify Employee select populated with active members of Customer Support Platform
    const empSelect = modal.querySelector('#inc-assign-employee');
    expect(empSelect).toBeTruthy();
    const options = Array.from(empSelect.querySelectorAll('option'));
    expect(options.some(o => o.textContent.includes('Sarathi'))).toBe(true);
    expect(options.some(o => o.textContent.includes('Aiden Cross'))).toBe(true);
  });

  test('allows manager to override AI-recommended team and refreshes employee list', async () => {
    incidentApi.getLatestTriage.mockResolvedValueOnce({
      id: 1,
      incident_id: 1,
      suggested_owner: 'Customer Support Platform',
      suggested_severity: 'high',
    });

    localStorage.setItem('user', JSON.stringify({
      id: 2,
      full_name: 'Elena Rostova',
      role: { id: 7, name: 'manager' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const assignBtn = Array.from(container.querySelectorAll('.inc-action-bar button')).find(b => b.textContent === 'Assign');
    await act(async () => {
      assignBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const modal = container.querySelector('.modal-overlay');
    const teamSelect = modal.querySelector('#inc-assign-team');

    // Override team to Recruitment AI (proj_2)
    await act(async () => {
      teamSelect.value = 'proj_2';
      teamSelect.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    // Verify Override banner appears
    const overrideBanner = modal.querySelector('[data-testid="ai-rec-overridden"]');
    expect(overrideBanner).toBeTruthy();
    expect(overrideBanner.textContent).toContain('Manager Override');
    expect(overrideBanner.textContent).toContain('Customer Support Platform');

    // Verify Employee select updated to Sanjith
    const empSelect = modal.querySelector('#inc-assign-employee');
    const options = Array.from(empSelect.querySelectorAll('option'));
    expect(options.some(o => o.textContent.includes('Sanjith'))).toBe(true);
  });

  test('submits valid assignment with selected team and employee and updates incident details', async () => {
    incidentApi.getLatestTriage.mockResolvedValueOnce({
      id: 1,
      incident_id: 1,
      suggested_owner: 'Customer Support Platform',
    });
    incidentApi.assignIncident.mockResolvedValueOnce({
      ...mockIncident,
      assigned_to: 222,
      assignee: { id: 222, full_name: 'Sarathi' },
      team_name: 'Customer Support Platform',
    });

    localStorage.setItem('user', JSON.stringify({
      id: 2,
      full_name: 'Elena Rostova',
      role: { id: 7, name: 'manager' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const assignBtn = Array.from(container.querySelectorAll('.inc-action-bar button')).find(b => b.textContent === 'Assign');
    await act(async () => {
      assignBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const modal = container.querySelector('.modal-overlay');
    const empSelect = modal.querySelector('#inc-assign-employee');
    const notesInput = modal.querySelector('#inc-assign-notes');

    // Select employee Sarathi (222)
    await act(async () => {
      empSelect.value = '222';
      empSelect.dispatchEvent(new Event('change', { bubbles: true }));
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(notesInput, 'Primary incident handler');
      notesInput.dispatchEvent(new Event('input', { bubbles: true }));
      notesInput.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // Click Assign Incident
    const submitBtn = Array.from(modal.querySelectorAll('button')).find(b => b.textContent === 'Assign Incident');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn.disabled).toBe(false);

    await act(async () => {
      submitBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    // Verify assignIncident was called with expected payload
    expect(incidentApi.assignIncident).toHaveBeenCalledWith(1, {
      assigned_to: 222,
      team_id: 'proj_4',
      team_name: 'Customer Support Platform',
      ai_recommended_team: 'Customer Support Platform',
      notes: 'Primary incident handler',
    });

    // Modal closed
    expect(container.querySelector('.modal-overlay')).toBeNull();

    // Incident detail updated with assignee and team badge
    const detailPanel = container.querySelector('#inc-detail');
    expect(detailPanel.textContent).toContain('Sarathi');
    expect(detailPanel.textContent).toContain('Customer Support Platform');
  });

  test('shows manual selection prompt when incident has no AI recommendation', async () => {
    incidentApi.getLatestTriage.mockRejectedValueOnce(new Error('No triage'));

    localStorage.setItem('user', JSON.stringify({
      id: 2,
      full_name: 'Elena Rostova',
      role: { id: 7, name: 'manager' },
    }));

    await act(async () => {
      root.render(
        <MemoryRouter>
          <IncidentManagement />
        </MemoryRouter>
      );
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const row = container.querySelector('.clickable-row');
    await act(async () => {
      row.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const assignBtn = Array.from(container.querySelectorAll('.inc-action-bar button')).find(b => b.textContent === 'Assign');
    await act(async () => {
      assignBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await new Promise(r => setTimeout(r, 60));
    });

    const modal = container.querySelector('.modal-overlay');
    expect(modal).toBeTruthy();

    // Verify manual banner appears
    const manualBanner = modal.querySelector('[data-testid="ai-rec-none"]');
    expect(manualBanner).toBeTruthy();
    expect(manualBanner.textContent).toContain('Manual Team Selection');
  });
});
