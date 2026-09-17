import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { MemoryRouter } from 'react-router-dom';
import OnlineMeeting from '../../pages/Meetings/OnlineMeeting';
import MicrophoneInput, { blobToBase64 } from './MicrophoneInput';
import { applyLiveEvent } from './useLiveMeeting';
import * as api from '../../api/onlineMeetingApi';

jest.mock('../../api/onlineMeetingApi', () => ({
  startOnlineMeeting: jest.fn(),
  getOnlineMeeting: jest.fn(),
  getOnlineTicket: jest.fn(),
  endOnlineMeeting: jest.fn(),
  onlineSocketUrl: () => 'ws://localhost/test',
}));

const session = {
  id: 'session-1', title: 'Project sync', status: 'active',
  started_at: new Date().toISOString(), transcript: [], participants: [],
  analysis: null, analysis_status: 'idle',
};
let container;
let root;
let sockets;

class TestSocket {
  static OPEN = 1;
  constructor() {
    this.readyState = 1;
    this.sent = [];
    sockets.push(this);
  }
  send(text) { this.sent.push(JSON.parse(text)); }
  close() { this.readyState = 3; }
  event(event) { this.onmessage({ data: JSON.stringify(event) }); }
}

beforeEach(() => {
  jest.clearAllMocks();
  sockets = [];
  global.IS_REACT_ACT_ENVIRONMENT = true;
  global.WebSocket = TestSocket;
  Object.defineProperty(global, 'crypto', { configurable: true, value: { randomUUID: () => 'client-uuid' } });
  api.getOnlineMeeting.mockResolvedValue(session);
  api.getOnlineTicket.mockResolvedValue({ ticket: 'test-ticket' });
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

test('event reducer deduplicates transcripts and preserves them on AI failure', () => {
  const event = { type: 'transcript', id: 'seg-1', speaker: 'Speaker 1', text: 'Deliver Friday' };
  const first = applyLiveEvent(session, event);
  expect(applyLiveEvent(first, event)).toBe(first);
  const failed = applyLiveEvent(first, { type: 'error', code: 'analysis_failed', message: 'Unavailable' });
  expect(failed.transcript).toHaveLength(1);
  expect(failed.analysis_status).toBe('error');
  const ended = { ...failed, status: 'ended' };
  expect(applyLiveEvent(failed, { type: 'meeting_ended', session: ended })).toBe(ended);
});

test('start failure remains visible without fake successful navigation', async () => {
  api.startOnlineMeeting.mockRejectedValue(new Error('Unavailable'));
  await render(<MemoryRouter><OnlineMeeting /></MemoryRouter>);
  await act(async () => Simulate.change(container.querySelector('input'), { target: { value: 'Sync' } }));
  await act(async () => Simulate.submit(container.querySelector('form')));
  expect(api.startOnlineMeeting).toHaveBeenCalledWith('Sync', 'client-uuid');
  expect(container.textContent).toContain('Could not start meeting');
});

test('live UI authenticates, submits text, renders real-shaped results and ends', async () => {
  await render(<MemoryRouter initialEntries={['/meetings/online?session=session-1']}><OnlineMeeting /></MemoryRouter>);
  const ws = sockets[0];
  await act(async () => {
    ws.onopen();
    ws.event({ type: 'authenticated' });
    ws.event({ type: 'join', speaker: 'Speaker 1' });
    ws.event({ type: 'snapshot', session });
  });
  expect(ws.sent[0]).toEqual({ type: 'auth', ticket: 'test-ticket' });
  expect(ws.sent[1]).toEqual({ type: 'join', client_id: 'client-uuid' });
  expect(container.textContent).toContain('CONNECTED');
  await act(async () => Simulate.change(container.querySelector('textarea'), { target: { value: 'Deliver Friday' } }));
  await act(async () => Simulate.submit(container.querySelector('form')));
  const sent = ws.sent.find((event) => event.type === 'transcript');
  expect(sent.text).toBe('Deliver Friday');
  await act(async () => {
    ws.event({ type: 'transcript', id: 'seg-1', text: sent.text, speaker: 'Speaker 1', start_ms: 0, source: 'manual' });
    ws.event({ type: 'ack', message_id: sent.message_id });
    ws.event({ type: 'analysis', summary: 'Delivery plan', decisions: ['Friday delivery'],
      key_points: ['Dashboard'], action_items: [{ description: 'Finish dashboard', assignee: 'Speaker 1', priority: 'high', confidence: 0.9 }],
      transcript_count: 1 });
  });
  expect(container.querySelector('[role="log"]').textContent).toContain('Deliver Friday');
  expect(container.textContent).toContain('Friday delivery');
  expect(container.textContent).toContain('Finish dashboard');
  expect(container.querySelector('textarea').value).toBe('');
  api.endOnlineMeeting.mockResolvedValue({ ...session, status: 'ending' });
  const end = [...container.querySelectorAll('button')].find((button) => button.textContent === 'End meeting');
  await act(async () => Simulate.click(end));
  expect(api.endOnlineMeeting).toHaveBeenCalledWith('session-1');
  await act(async () => ws.event({ type: 'meeting_ended', session: { ...session, status: 'ended' } }));
  expect(container.textContent).toContain('ENDED');
  expect(container.querySelector('textarea')).toBeNull();
});

test('microphone unavailability is visible and does not submit fake audio', async () => {
  const onError = jest.fn();
  const sendInput = jest.fn();
  await render(<MicrophoneInput disabled={false} startedAt={session.started_at}
    onError={onError} onBusy={() => {}} sendInput={sendInput} />);
  await act(async () => Simulate.click(container.querySelector('button')));
  expect(onError).toHaveBeenCalled();
  expect(sendInput).not.toHaveBeenCalled();
});

test('audio encoder sends only base64 payload', async () => {
  expect(await blobToBase64(new Blob(['clip'], { type: 'audio/webm' }))).toBe('Y2xpcA==');
});