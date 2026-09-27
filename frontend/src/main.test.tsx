import { act } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
const render = vi.hoisted(() => vi.fn());
vi.mock('react-dom/client', () => ({default:{createRoot: () => ({render})}}));
vi.mock('./App', () => ({default: () => null}));
import { AuthGate } from './auth/AuthGate';
import { AuthProvider } from './auth/AuthProvider';
it('places the application behind the session provider and gate at the real entrypoint', async () => {
  await act(async () => { await import('./main'); });
  const strict = render.mock.calls[0][0];
  const query = strict.props.children;
  expect(query.props.children.type).toBe(AuthProvider);
  expect(query.props.children.props.children.type).toBe(AuthGate);
});
