import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import PerformancePage from '../../pages/Performance/PerformancePage';

const { usePerformance, useAuth } = vi.hoisted(() => ({
  usePerformance: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/usePerformance', () => ({ usePerformance }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));

const baseHookValue = {
  overview: {
    total_applications: 3,
    decided_applications: 1,
    status_counts: { APPROVED: 1, PROCESSING: 2 },
    avg_waiting_seconds: 86400,
    avg_processing_seconds: 3600,
    avg_review_seconds: null,
    avg_turnaround_seconds: 90000,
    total_resubmissions: 1,
    total_missing_document_cycles: 2,
  },
  overviewLoading: false,
  overviewError: null,
  rows: [],
  total: 0,
  loading: false,
  error: null,
  query: '',
  status: '',
  pageCount: 1,
  currentPage: 0,
  onQueryChange: vi.fn(),
  onStatusChange: vi.fn(),
  onGoToPage: vi.fn(),
  onRefresh: vi.fn(),
};

function makeRow(overrides = {}) {
  return {
    application_id: 42,
    application_name: 'TMA Khal',
    status: 'APPROVED',
    submitted_at: '2026-08-01T00:00:00Z',
    decided_at: '2026-08-05T00:00:00Z',
    created_by: 'operator1',
    waiting_seconds: 172800,
    processing_seconds: 7200,
    review_seconds: 3600,
    total_turnaround_seconds: 345600,
    resubmissions: 1,
    missing_document_cycles: 1,
    waiting_spans: [
      { label: 'Documents requested', start: '2026-08-01T00:00:00Z', end: '2026-08-02T00:00:00Z', duration_seconds: 86400, open: false },
    ],
    processing_spans: [],
    review_spans: [],
    ...overrides,
  };
}

function renderPage() {
  return render(<PerformancePage />);
}

describe('PerformancePage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the overview cards and empty state for no applications', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    usePerformance.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    expect(screen.getByText('1 decided')).toBeInTheDocument();
    expect(screen.getByText('1d')).toBeInTheDocument();
    expect(screen.getByText(/avg waiting for documents/i)).toBeInTheDocument();
    expect(screen.getByText(/document follow-ups/i)).toBeInTheDocument();
    expect(screen.getByText(/no applications found/i)).toBeInTheDocument();
  });

  it('shows the access-denied state for a non-IT user', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    usePerformance.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
  });

  it('allows the Employee (development all-access) user to view the page', () => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
    usePerformance.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no applications found/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Refresh performance figures/i })).toBeInTheDocument();
  });

  it('renders a row with formatted durations and expands its evidence spans', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    usePerformance.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
    });

    renderPage();

    expect(screen.getByText(/#42/i)).toBeInTheDocument();
    expect(screen.getByText('2d')).toBeInTheDocument();
    expect(screen.getByText(/document follow-ups: 2/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /show evidence/i }));

    expect(screen.getAllByText(/waiting for documents/i).length).toBeGreaterThan(0);
    expect(screen.getByText('Documents requested')).toBeInTheDocument();
    expect(screen.getAllByText(/1d/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/no recorded spans/i).length).toBeGreaterThan(0);
  });

  it('shows an open span as still running rather than a duration', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    usePerformance.mockReturnValue({
      ...baseHookValue,
      rows: [
        makeRow({
          waiting_seconds: null,
          waiting_spans: [
            { label: 'Documents requested', start: '2026-08-01T00:00:00Z', end: null, duration_seconds: null, open: true },
          ],
        }),
      ],
      total: 1,
    });

    renderPage();

    fireEvent.click(screen.getByRole('button', { name: /show evidence/i }));
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText(/→ now/i)).toBeInTheDocument();
  });

  it('shows the error state when the fetch fails', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    usePerformance.mockReturnValue({ ...baseHookValue, error: 'Network error' });

    renderPage();

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });
});
