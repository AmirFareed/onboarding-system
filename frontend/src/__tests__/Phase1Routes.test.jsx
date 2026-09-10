import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import App from '../App';
import * as authService from '../auth/authService';

vi.mock('../auth/authService', () => ({
  getCurrentUser: vi.fn(() =>
    Promise.resolve({ user: { id: 1, name: 'Test Employee', role: 'EMPLOYEE' } })
  ),
  login: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
}));

vi.mock('../services/applications', () => ({
  listApplications: vi.fn(() => Promise.resolve({ items: [] })),
  createApplication: vi.fn(),
}));

vi.mock('../services/operatorWorkflow', () => ({
  listValidationQueue: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  getValidationHistory: vi.fn(() => Promise.resolve({ entries: [], total: 0 })),
  requestDocuments: vi.fn(),
  rejectApplication: vi.fn(),
  submitApplication: vi.fn(),
}));

vi.mock('../services/applicationHistory', () => ({
  listApplicationHistory: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  getApplicationTimeline: vi.fn(() => Promise.resolve({ events: [] })),
}));

vi.mock('../services/performance', () => ({
  getPerformanceOverview: vi.fn(() =>
    Promise.resolve({ total_applications: 0, decided_applications: 0, status_counts: {} })
  ),
  listPerformanceApplications: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
}));

vi.mock('../services/systemLogs', () => ({
  listSystemLogs: vi.fn(() => Promise.resolve({ items: [], total: 0, offset: 0, limit: 50 })),
  getSystemLog: vi.fn(),
}));

describe('Phase 1 frontend routes', () => {
  it('renders the Validation page at /validation', async () => {
    render(
      <MemoryRouter initialEntries={['/validation']}>
        <App />
      </MemoryRouter>
    );

    expect(
      await screen.findByText(/no applications to validate/i)
    ).toBeInTheDocument();
  });

  it('renders the Application History page at /application-history for allowed roles and denies for others', async () => {
    // Employee (development all-access) should be allowed
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 2, name: 'Employee', role: 'EMPLOYEE' } })
    );
    render(
      <MemoryRouter initialEntries={['/application-history']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/no applications found/i)).toBeInTheDocument();

    // IT user should be allowed
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 3, name: 'It User', role: 'IT' } })
    );
    render(
      <MemoryRouter initialEntries={['/application-history']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/no applications found/i)).toBeInTheDocument();

    // Operator should be denied
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 4, name: 'Operator', role: 'OPERATOR' } })
    );
    render(
      <MemoryRouter initialEntries={['/application-history']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();

    // Reviewer should be denied
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 5, name: 'Reviewer', role: 'REVIEWER' } })
    );
    render(
      <MemoryRouter initialEntries={['/application-history']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
  });

  it('renders the Performance page at /performance for allowed roles and denies for others', async () => {
    // Employee allowed
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 6, name: 'Employee', role: 'EMPLOYEE' } })
    );
    render(
      <MemoryRouter initialEntries={['/performance']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/no applications found/i)).toBeInTheDocument();

    // IT allowed
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 7, name: 'It User', role: 'IT' } })
    );
    render(
      <MemoryRouter initialEntries={['/performance']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/no applications found/i)).toBeInTheDocument();

    // Operator denied
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 8, name: 'Operator', role: 'OPERATOR' } })
    );
    render(
      <MemoryRouter initialEntries={['/performance']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();

    // Reviewer denied
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 9, name: 'Reviewer', role: 'REVIEWER' } })
    );
    render(
      <MemoryRouter initialEntries={['/performance']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
  });

  it('renders the System Logs page at /system-logs for allowed roles and denies for others', async () => {
    // Employee allowed
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 10, name: 'Employee', role: 'EMPLOYEE' } })
    );
    render(
      <MemoryRouter initialEntries={['/system-logs']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/no log entries found/i)).toBeInTheDocument();

    // IT allowed
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 11, name: 'It User', role: 'IT' } })
    );
    render(
      <MemoryRouter initialEntries={['/system-logs']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/no log entries found/i)).toBeInTheDocument();

    // Operator denied
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 12, name: 'Operator', role: 'OPERATOR' } })
    );
    render(
      <MemoryRouter initialEntries={['/system-logs']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();

    // Reviewer denied
    vi.mocked(authService.getCurrentUser).mockImplementationOnce(() =>
      Promise.resolve({ user: { id: 13, name: 'Reviewer', role: 'REVIEWER' } })
    );
    render(
      <MemoryRouter initialEntries={['/system-logs']}>
        <App />
      </MemoryRouter>
    );
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument();
  });
});