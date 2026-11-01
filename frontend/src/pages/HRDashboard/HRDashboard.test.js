import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';

import HRDashboard from './HRDashboard';
import * as recruitmentApi from '../../api/recruitmentApi';

jest.mock('../../api/recruitmentApi', () => ({
  createJob: jest.fn(),
  listJobs: jest.fn(),
  updateJob: jest.fn(),
  deleteJob: jest.fn(),
  bulkUploadResumes: jest.fn(),
  listResumes: jest.fn(),
  getResume: jest.fn(),
  updateResume: jest.fn(),
  deleteResume: jest.fn(),
  analyzeResumes: jest.fn(),
  getRecruitmentStats: jest.fn(),
  getTopCandidates: jest.fn(),
  sendInterviewInvite: jest.fn(),
}));

const MOCK_JOBS = [
  { id: 1, title: 'Python Backend Engineer', required_skills: 'Python, FastAPI, Docker', status: 'active', min_education: "Bachelor's Degree", experience_level: 'mid' },
];

const MOCK_TOP_CANDIDATES = [
  {
    rank: 1,
    resume_id: 101,
    candidate_name: 'Sophia Patel',
    candidate_email: 'sophia@example.com',
    file_name: 'sophia_resume.pdf',
    ocr_status: 'extracted',
    ai_score: 95.0,
    recommendation: 'selected',
    matched_skills: 'Python, FastAPI, Docker, SQL',
    missing_skills: 'None',
    application_status: 'Shortlisted',
    interview_invited: false,
    meets_criteria: true,
  },
  {
    rank: 2,
    resume_id: 102,
    candidate_name: 'Marcus Vance',
    candidate_email: 'marcus@example.com',
    file_name: 'marcus_resume.pdf',
    ocr_status: 'analysed',
    ai_score: 84.0,
    recommendation: 'hold',
    matched_skills: 'Python, Docker',
    missing_skills: 'FastAPI',
    application_status: 'Interview Scheduled',
    interview_invited: true,
    meets_criteria: true,
  },
];

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  localStorage.setItem('user', JSON.stringify({ id: 1, full_name: 'HR Lead', role: { name: 'hr_manager' } }));
  recruitmentApi.listJobs.mockResolvedValue(MOCK_JOBS);
  recruitmentApi.getRecruitmentStats.mockResolvedValue({ open_positions: 1, applications: 2, waiting: 0, shortlisted: 1, rejected: 0 });
  recruitmentApi.listResumes.mockResolvedValue([]);
  recruitmentApi.getTopCandidates.mockResolvedValue(MOCK_TOP_CANDIDATES);
  recruitmentApi.sendInterviewInvite.mockResolvedValue({
    status: 'success',
    message: 'Interview invitation sent to sophia@example.com (simulated delivery; SMTP unconfigured).',
    resume_id: 101,
    recipient_email: 'sophia@example.com',
    application_status: 'Interview Scheduled',
  });

  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function renderDashboard() {
  await act(async () => root.render(<MemoryRouter><HRDashboard /></MemoryRouter>));
}

test('loads and displays top-N candidates with ranks, scores, skills, and statuses', async () => {
  await renderDashboard();

  // Select job and load
  const select = container.querySelector('.controls-row select.field-select');
  await act(async () => {
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });

  const loadBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes('Load'));
  await act(async () => {
    loadBtn.click();
  });

  // Verify Top-N ranking controls are present
  expect(container.textContent).toContain('Top-N Candidate Ranking');
  expect(container.textContent).toContain('Top 5');
  expect(container.textContent).toContain('Top 10');
  expect(container.textContent).toContain('Top 15');
  expect(container.textContent).toContain('Top 20');

  // Verify candidate rows
  expect(container.textContent).toContain('Sophia Patel');
  expect(container.textContent).toContain('#1');
  expect(container.textContent).toContain('95%');
  expect(container.textContent).toContain('Shortlisted');
  expect(container.textContent).toContain('Python');

  // Verify Marcus Vance row with invited badge
  expect(container.textContent).toContain('Marcus Vance');
  expect(container.textContent).toContain('#2');
  expect(container.textContent).toContain('✓ Invited');
});

test('changing top-N selector calls getTopCandidates with requested count', async () => {
  await renderDashboard();

  // Select job and load
  const select = container.querySelector('.controls-row select.field-select');
  await act(async () => {
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });

  const loadBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes('Load'));
  await act(async () => {
    loadBtn.click();
  });

  const top10Btn = Array.from(container.querySelectorAll('.top-n-btn')).find((b) => b.textContent.includes('Top 10'));
  expect(top10Btn).toBeTruthy();

  await act(async () => {
    top10Btn.click();
  });

  expect(recruitmentApi.getTopCandidates).toHaveBeenCalledWith(1, 10);
});

test('accept for interview opens modal and sends invitation email', async () => {
  await renderDashboard();

  // Select job and load
  const select = container.querySelector('.controls-row select.field-select');
  await act(async () => {
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });

  const loadBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes('Load'));
  await act(async () => {
    loadBtn.click();
  });

  const inviteBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes('Accept for Interview'));
  expect(inviteBtn).toBeTruthy();

  await act(async () => {
    inviteBtn.click();
  });

  // Modal is opened
  expect(container.textContent).toContain('Accept & Invite for Interview');
  expect(container.textContent).toContain('Dear Sophia Patel');
  expect(container.textContent).toContain('EnterpriseAI');

  // Click Send Interview Invitation
  const sendBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent.includes('Send Interview Invitation'));
  expect(sendBtn).toBeTruthy();

  await act(async () => {
    sendBtn.click();
  });

  expect(recruitmentApi.sendInterviewInvite).toHaveBeenCalledWith(101, expect.objectContaining({
    recipient_email: 'sophia@example.com',
    candidate_name: 'Sophia Patel',
  }));
});

