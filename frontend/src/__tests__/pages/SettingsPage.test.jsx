import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SettingsPage from '../../pages/Settings/SettingsPage';

const { useAuth, useToast } = vi.hoisted(() => ({
  useAuth: vi.fn(),
  useToast: vi.fn(),
}));

vi.mock('../../hooks/useAuth', () => ({ useAuth }));
vi.mock('../../components/common/Toast/ToastContext', () => ({ useToast }));
vi.mock('../../utils/preferences', () => ({
  getPreferences: vi.fn(() => ({})),
  setPreference: vi.fn(),
}));

const baseUser = {
  id: 1,
  employee_id: 'EMP-1001',
  email: 'employee@fintech.local',
  name: 'Test Employee',
  role: 'Verification Officer',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>
  );
}

describe('SettingsPage administration section', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the Feedback and Continuous Learning links for an IT user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'IT' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    const feedback = await screen.findByRole('link', { name: /feedback/i });
    expect(feedback).toBeInTheDocument();
    expect(feedback).toHaveAttribute('href', '/feedback');
    const learning = screen.getByRole('link', { name: /continuous learning/i });
    expect(learning).toHaveAttribute('href', '/continuous-learning');
  });

  it('shows the Feedback and Continuous Learning links for the Employee (supervisor) account', async () => {
    useAuth.mockReturnValue({
      user: baseUser,
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    const feedback = await screen.findByRole('link', { name: /feedback/i });
    expect(feedback).toBeInTheDocument();
    expect(feedback).toHaveAttribute('href', '/feedback');
    const learning = screen.getByRole('link', { name: /continuous learning/i });
    expect(learning).toHaveAttribute('href', '/continuous-learning');
  });

  it('hides the Feedback and Continuous Learning links for an OPERATOR user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'OPERATOR' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.queryByRole('link', { name: /feedback/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /continuous learning/i })).not.toBeInTheDocument();
  });

  it('hides the Feedback and Continuous Learning links for a REVIEWER user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'REVIEWER' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.queryByRole('link', { name: /feedback/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /continuous learning/i })).not.toBeInTheDocument();
  });

  it('hides the administration section entirely for an OPERATOR user', async () => {
    useAuth.mockReturnValue({
      user: { ...baseUser, role: 'OPERATOR' },
      authenticated: true,
      loading: false,
      logout: vi.fn(),
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.queryByRole('heading', { name: /administration/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /feedback/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /continuous learning/i })).not.toBeInTheDocument();
  });
});