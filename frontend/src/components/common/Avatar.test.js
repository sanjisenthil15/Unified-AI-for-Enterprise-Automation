import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Avatar from './Avatar';

let container;
let root;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('Avatar Component', () => {
  test('renders initials fallback when photo is missing', async () => {
    await act(async () => {
      root.render(<Avatar name="Elena Rostova" email="elena@example.com" size={40} />);
    });

    const el = container.querySelector('.avatar');
    expect(el).not.toBeNull();
    expect(el.style.width).toBe('40px');
    expect(el.style.height).toBe('40px');
    expect(el.getAttribute('title')).toBe('Elena Rostova');
  });

  test('applies exact square dimensions preventing stretch distortion', async () => {
    await act(async () => {
      root.render(<Avatar name="Aiden Cross" size={48} />);
    });

    const el = container.querySelector('.avatar');
    expect(el.style.width).toBe('48px');
    expect(el.style.height).toBe('48px');
    expect(el.style.minWidth).toBe('48px');
    expect(el.style.minHeight).toBe('48px');
    expect(el.style.maxWidth).toBe('48px');
    expect(el.style.maxHeight).toBe('48px');
  });
});
