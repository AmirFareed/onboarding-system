import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import App from '../App';

// AuthProvider calls authService.getCurrentUser() on mount to restore the
// session; mocking the service (rather than the App tree) keeps this a real
// render of every provider and route while avoiding an actual network call.
vi.mock('../auth/authService', () => ({
  getCurrentUser: vi.fn(() =>
    Promise.resolve({ user: { id: 1, name: 'Test Operator', role: 'Verification Officer' } })
  ),
  login: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
}));

// ApplicationsProvider (mounted inside the protected layout) fetches the
// application list on mount; an authenticated render reaches it, so it needs
// mocking too, same reasoning as above.
vi.mock('../services/applications', () => ({
  listApplications: vi.fn(() => Promise.resolve({ items: [] })),
  createApplication: vi.fn(),
}));

describe('App', () => {
  it('renders the authenticated dashboard without crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Welcome back!/i)).toBeInTheDocument();
  });

  it('redirects to the login page when there is no session', async () => {
    const { getCurrentUser } = await import('../auth/authService');
    getCurrentUser.mockRejectedValueOnce(new Error('unauthenticated'));

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });
});
