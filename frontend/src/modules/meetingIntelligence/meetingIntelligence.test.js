/**
 * Render smoke test for the Meeting Intelligence UI.
 * Renders each component with API-shaped props (incl. empty / edge cases)
 * and checks the formatting helpers. Runs with `npm test`.
 */
import React, { act } from 'react';
import { renderToString } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';

import SummaryPanel from './SummaryPanel';
import TranscriptViewer from './TranscriptViewer';
import ActionItemList from './ActionItemList';
import MeetingList from './MeetingList';
import AudioUpload from './AudioUpload';
import { statusBadge, formatDuration, formatTimestamp, isInProgress } from './helpers';

// AudioUpload loads the project picker on mount. A plain function (not
// jest.fn) so CRA's resetMocks doesn't wipe the resolved value between tests.
jest.mock('../../api/employeeApi', () => ({
  listProjects: () => Promise.resolve([]),
}));

const analysis = {
  meeting_id: 1, summary: 'They discussed hiring three developers.',
  key_points: ['Workload too high', 'Hire 3'], decisions: ['Hire 3 backend devs'],
  sentiment: 'neutral', model_provider: 'gemini', model_name: 'gemini-3.6-flash',
  generated_at: new Date().toISOString(),
};
const transcript = {
  meeting_id: 1, language: 'en', whisper_model: 'base', segment_count: 2,
  full_text: 'Speaker 1: hi. Speaker 2: bye.',
  speakers: [
    { id: 1, label: 'Speaker 1', segment_count: 1, total_speaking_sec: 3 },
    { id: 2, label: 'Speaker 2', display_name: null, segment_count: 1, total_speaking_sec: 4 },
  ],
  segments: [
    { seq: 0, start_ms: 0, end_ms: 3000, speaker_id: 1, speaker_label: 'Speaker 1', text: 'hi' },
    { seq: 1, start_ms: 3000, end_ms: 7000, speaker_id: 2, speaker_label: 'Speaker 2', text: 'bye' },
  ],
};
const items = [{
  id: 1, description: 'Post the jobs by Friday', assignee_name_raw: 'Speaker 2',
  assigned_to_user_id: null, assigned_to_employee_id: null, assignment_method: 'unassigned',
  due_date: null, priority: 'high', status: 'pending', source: 'ai', ai_confidence: 0.9,
  created_at: new Date().toISOString(),
}];
const meetings = [
  { id: 1, title: 'Hiring sync', status: 'processing', duration_sec: null, meeting_date: null, created_at: new Date().toISOString() },
  { id: 2, title: 'Done one', status: 'completed', duration_sec: 754, meeting_date: '2026-09-01', created_at: '2026-09-01' },
  { id: 3, title: 'Broken one', status: 'failed', duration_sec: null, meeting_date: null, created_at: '2026-09-02' },
];

test('helpers behave', () => {
  expect(statusBadge('completed')).toEqual({ label: 'Completed', badge: 'green' });
  expect(statusBadge('transcribing').badge).toBe('amber');
  expect(isInProgress('analyzing')).toBe(true);
  expect(isInProgress('completed')).toBe(false);
  expect(formatDuration(754)).toBe('12m 34s');
  expect(formatDuration(null)).toBe('—');
  expect(formatTimestamp(65000)).toBe('01:05');
});

test('components render with API-shaped props', () => {
  const noop = () => {};
  expect(renderToString(<SummaryPanel analysis={analysis} />)).toContain('Hire 3 backend devs');
  expect(renderToString(<SummaryPanel analysis={null} />)).toBe('');
  expect(renderToString(<TranscriptViewer transcript={transcript} />)).toContain('Speaker 1');
  expect(renderToString(<TranscriptViewer transcript={{ ...transcript, segments: [], speakers: [] }} />)).toContain('Speaker 1: hi');
  expect(renderToString(<ActionItemList items={items} />)).toContain('Post the jobs by Friday');
  expect(renderToString(<ActionItemList items={[]} />)).toContain('No action items');
  expect(renderToString(<MeetingList meetings={meetings} loading={false} onSelect={noop} />)).toContain('Processing');
  expect(renderToString(<MeetingList meetings={[]} loading={false} onSelect={noop} />)).toContain('No meetings yet');
  const upload = renderToString(<AudioUpload onUploaded={noop} onCancel={noop} />);
  expect(upload).toContain('Record a new meeting');
  expect(upload).toContain('Upload video or audio from device');
  expect(upload).not.toContain('Meeting title');
});

test('AudioUpload: choosing "Upload" reveals the meeting details form', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AudioUpload onUploaded={() => {}} onCancel={() => {}} />));
    expect(container.textContent).not.toContain('Meeting title');

    const uploadChoice = [...container.querySelectorAll('button')]
      .find((b) => b.textContent.includes('Upload video or audio from device'));
    await act(async () => Simulate.click(uploadChoice));

    expect(container.textContent).toContain('Meeting title');
    expect(container.querySelector('input[type="file"]')).not.toBeNull();
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
});
