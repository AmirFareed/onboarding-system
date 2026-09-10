import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import Dashboard from '../../pages/Dashboard/Dashboard';

const { useAuth } = vi.hoisted(() => ({
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/useAuth', () => ({ useAuth }));
vi.mock('../../components/dashboard/QuickActions/QuickActions', () => ({
  default: () => null,
}));
vi.mock('../../components/dashboard/RecentApplications/RecentApplications', () => ({
  default: () => null,
}));
vi.mock('../../components/dashboard/RecentActivity/RecentActivity', () => ({
  default: () => null,
}));

describe('Dashboard welcome text', () => {
  it('renders the Employee welcome description', () => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
    render(<Dashboard />);
    expect(
      screen.getByText("Here's an overview of your financial document verification workspace.")
    ).toBeInTheDocument();
  });

  it('renders the OPERATOR welcome description', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    render(<Dashboard />);
    expect(
      screen.getByText('Manage document intake, completeness checks, and application processing.')
    ).toBeInTheDocument();
  });

  it('renders the REVIEWER welcome description', () => {
    useAuth.mockReturnValue({ user: { role: 'REVIEWER' } });
    render(<Dashboard />);
    expect(
      screen.getByText('Review validated applications and make final verification decisions.')
    ).toBeInTheDocument();
  });

  it('renders the IT welcome description', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    render(<Dashboard />);
    expect(
      screen.getByText('Monitor application processing and system activity.')
    ).toBeInTheDocument();
  });

  it('always renders the shared welcome heading', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    render(<Dashboard />);
    expect(screen.getByText('Welcome back!')).toBeInTheDocument();
  });
});