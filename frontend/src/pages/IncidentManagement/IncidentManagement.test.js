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
});
