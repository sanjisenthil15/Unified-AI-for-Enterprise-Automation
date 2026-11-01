import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import CreateTicketModal from './components/CreateTicketModal';

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
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

test('Successful ticket creation calls onClose only after submission resolves', async () => {
  const onSubmit = jest.fn().mockResolvedValue({ id: 501, subject: 'Payment bug' });
  const onClose = jest.fn();

  await render(
    <CreateTicketModal
      initialData={{ subject: 'Billing issue', description: 'Charged twice on card' }}
      categories={[{ id: 1, name: 'Billing' }]}
      onSubmit={onSubmit}
      onClose={onClose}
    />
  );

  const form = container.querySelector('form');
  await act(async () => {
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });

  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({
      subject: 'Billing issue',
      description: 'Charged twice on card',
    })
  );
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('Failed ticket creation displays error message and does not close modal or clear input', async () => {
  const onSubmit = jest.fn().mockRejectedValue({
    response: { data: { detail: 'Database persistence failed for support ticket.' } },
  });
  const onClose = jest.fn();

  await render(
    <CreateTicketModal
      initialData={{ subject: 'Database down', description: 'Postgres unreachable' }}
      categories={[{ id: 1, name: 'Infrastructure' }]}
      onSubmit={onSubmit}
      onClose={onClose}
    />
  );

  const form = container.querySelector('form');
  await act(async () => {
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });

  expect(onSubmit).toHaveBeenCalledTimes(1);
  // Modal must NOT close on error
  expect(onClose).not.toHaveBeenCalled();

  // Error message must be rendered
  const errorBox = container.querySelector('.cs-form-error');
  expect(errorBox).not.toBeNull();
  expect(errorBox.textContent).toContain('Database persistence failed for support ticket.');

  // Form inputs must preserve their values so user does not lose input
  const subjectInput = container.querySelector('input[type="text"]');
  expect(subjectInput.value).toBe('Database down');
});

test('Rejects submission if subject or description are empty', async () => {
  const onSubmit = jest.fn();
  const onClose = jest.fn();

  await render(
    <CreateTicketModal
      initialData={{ subject: '', description: '' }}
      categories={[]}
      onSubmit={onSubmit}
      onClose={onClose}
    />
  );

  const form = container.querySelector('form');
  await act(async () => {
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });

  expect(onSubmit).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  const errorBox = container.querySelector('.cs-form-error');
  expect(errorBox).not.toBeNull();
  expect(errorBox.textContent).toContain('Subject is required.');
});

