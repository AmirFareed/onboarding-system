import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ApplicationsPage from '../../pages/Applications/ApplicationsPage';

const { useApplications, useApplicationsStore, useLastOpenedApplication } = vi.hoisted(() => ({
  useApplications: vi.fn(),
  useApplicationsStore: vi.fn(),
  useLastOpenedApplication: vi.fn(),
}));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
const { useToast } = vi.hoisted(() => ({
  useToast: vi.fn(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() })),
}));

vi.mock('../../hooks/useApplications', () => ({ useApplications }));
vi.mock('../../store/ApplicationsContext', () => ({ useApplicationsStore }));
vi.mock('../../hooks/useLastOpenedApplication', () => ({ useLastOpenedApplication }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));
// ApplicationRow (rendered via ApplicationTable) now offers a delete action
// that calls useToast() for success/error feedback -- mocked here the same
// way every other hook in this render tree is, since this test suite mocks
// hooks shallowly rather than mounting real providers (no ToastProvider is
// mounted around <ApplicationsPage /> in renderPage() below).
vi.mock('../../components/common/Toast/ToastContext', () => ({ useToast }));
vi.mock('../../utils/preferences', () => ({
  getPreference: vi.fn(() => true),
}));

const baseHookValue = {
  applications: [],
  total: 0,
  loading: false,
  error: null,
  reload: vi.fn(),
  searchTerm: '',
  statusFilter: '',
  sortKey: 'submitted_at',
  sortDir: 'desc',
  onSearchChange: vi.fn(),
  onStatusChange: vi.fn(),
  onSortChange: vi.fn(),
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ApplicationsPage />
    </MemoryRouter>
  );
}

describe('ApplicationsPage', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when there are no applications', () => {
    useApplications.mockReturnValue(baseHookValue);
    useApplicationsStore.mockReturnValue({ applications: [] });
    useLastOpenedApplication.mockReturnValue({ lastOpenedId: null, clear: vi.fn() });

    renderPage();

    expect(screen.getByText(/no applications yet/i)).toBeInTheDocument();
  });

  it('renders a row for each application from the store', () => {
    useApplications.mockReturnValue({
      ...baseHookValue,
      applications: [
        {
          id: 42,
          name: 'Ali Khan',
          status: 'IN_PROGRESS',
          submitted_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-02T00:00:00Z',
          created_by: 'operator1',
        },
      ],
      total: 1,
    });
    useApplicationsStore.mockReturnValue({ applications: [{ id: 42 }] });
    useLastOpenedApplication.mockReturnValue({ lastOpenedId: null, clear: vi.fn() });

    renderPage();

    expect(screen.getByText('#42')).toBeInTheDocument();
    expect(screen.getByText('Ali Khan')).toBeInTheDocument();
    expect(screen.getByText('1 application')).toBeInTheDocument();
  });

  it('shows the error state and retries on demand', () => {
    const reload = vi.fn();
    useApplications.mockReturnValue({ ...baseHookValue, error: 'Network error', reload });
    useApplicationsStore.mockReturnValue({ applications: [] });
    useLastOpenedApplication.mockReturnValue({ lastOpenedId: null, clear: vi.fn() });

    renderPage();

    expect(
      screen.getByText(/unable to load applications/i)
    ).toBeInTheDocument();
  });

  it('hides the resume chip when the stored id is not in the current application list', () => {
    useApplications.mockReturnValue(baseHookValue);
    useApplicationsStore.mockReturnValue({ applications: [{ id: 99 }] });
    useLastOpenedApplication.mockReturnValue({ lastOpenedId: 8267, clear: vi.fn() });

    renderPage();

    expect(screen.queryByText(/resume application/i)).not.toBeInTheDocument();
  });

  it('shows the resume chip when the stored id is in the current application list', () => {
    useApplications.mockReturnValue(baseHookValue);
    useApplicationsStore.mockReturnValue({ applications: [{ id: 8267 }] });
    useLastOpenedApplication.mockReturnValue({ lastOpenedId: 8267, clear: vi.fn() });

    renderPage();

    expect(screen.getByText(/resume application #8267/i)).toBeInTheDocument();
  });
});
