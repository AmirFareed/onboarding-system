import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import SystemLogsPage from '../../pages/SystemLogs/SystemLogsPage';

const { useSystemLogs, useAuth } = vi.hoisted(() => ({
  useSystemLogs: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/useSystemLogs', () => ({ useSystemLogs }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));

const baseHookValue = {
  rows: [],
  total: 0,
  loading: false,
  error: null,
  actor: '',
  eventType: '',
  severity: '',
  dateFrom: '',
  dateTo: '',
  query: '',
  includeOrphaned: false,
  pageCount: 1,
  currentPage: 0,
  selectedId: null,
  detail: null,
  detailLoading: false,
  detailError: null,
  onActorChange: vi.fn(),
  onEventTypeChange: vi.fn(),
  onSeverityChange: vi.fn(),
  onDateFromChange: vi.fn(),
  onDateToChange: vi.fn(),
  onQueryChange: vi.fn(),
  onIncludeOrphanedChange: vi.fn(),
  onGoToPage: vi.fn(),
  onSelect: vi.fn(),
  onCloseDetail: vi.fn(),
  onRefresh: vi.fn(),
};

function makeRow(overrides = {}) {
  return {
    id: 101,
    application_id: 42,
    username: 'operator.one',
    actor_role: 'OPERATOR',
    action: 'DOCUMENTS_REQUESTED',
    severity: 'WARNING',
    previous_status: 'SUBMITTED',
    new_status: 'NEEDS_DOCUMENTS',
    document_id: null,
    performed_at: '2026-08-01T00:00:00Z',
    details: { missing_document_types: ['ONE_LINK_LETTER'] },
    ...overrides,
  };
}

function renderPage() {
  return render(<SystemLogsPage />);
}

describe('SystemLogsPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when no log entries exist', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no log entries found/i)).toBeInTheDocument();
  });

  it('renders a row with actor, action and severity for each log entry', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
    });

    renderPage();

    expect(screen.getByText('operator.one')).toBeInTheDocument();
    expect(screen.getByText('OPERATOR')).toBeInTheDocument();
    expect(screen.getByText('DOCUMENTS_REQUESTED')).toBeInTheDocument();
    expect(screen.getByText('WARNING')).toBeInTheDocument();
    expect(screen.getByText('#42')).toBeInTheDocument();
    expect(screen.getByText(/1 entry/i)).toBeInTheDocument();
  });

  it('shows the access-denied state for a non-IT user', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useSystemLogs.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /refresh/i })).not.toBeInTheDocument();
  });

  it('allows the Employee (development all-access) user to view the page', () => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
    useSystemLogs.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no log entries found/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /refresh/i })).toBeInTheDocument();
  });

  it('triggers a search when the user submits the query', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onQueryChange = vi.fn();
    useSystemLogs.mockReturnValue({ ...baseHookValue, onQueryChange });

    renderPage();

    fireEvent.change(screen.getByLabelText(/search system logs/i), {
      target: { value: 'operator.one' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    expect(onQueryChange).toHaveBeenCalledWith('operator.one');
  });

  it('calls the filter handlers when actor, action and severity filters change', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onActorChange = vi.fn();
    const onEventTypeChange = vi.fn();
    const onSeverityChange = vi.fn();
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      onActorChange,
      onEventTypeChange,
      onSeverityChange,
    });

    renderPage();

    fireEvent.change(screen.getByLabelText(/filter by actor/i), {
      target: { value: 'reviewer1' },
    });
    expect(onActorChange).toHaveBeenCalledWith('reviewer1');

    fireEvent.change(screen.getByLabelText(/filter by action/i), {
      target: { value: 'ACTION_VALIDATED' },
    });
    expect(onEventTypeChange).toHaveBeenCalledWith('ACTION_VALIDATED');

    fireEvent.change(screen.getByLabelText(/filter by severity/i), {
      target: { value: 'ERROR' },
    });
    expect(onSeverityChange).toHaveBeenCalledWith('ERROR');
  });

  it('calls the date filter handlers when the date range changes', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onDateFromChange = vi.fn();
    const onDateToChange = vi.fn();
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      onDateFromChange,
      onDateToChange,
    });

    renderPage();

    fireEvent.change(screen.getByLabelText(/filter from date/i), {
      target: { value: '2026-08-01' },
    });
    expect(onDateFromChange).toHaveBeenCalledWith('2026-08-01');

    fireEvent.change(screen.getByLabelText(/filter to date/i), {
      target: { value: '2026-08-20' },
    });
    expect(onDateToChange).toHaveBeenCalledWith('2026-08-20');
  });

  it('is unchecked by default and calls the handler when the orphaned-entries toggle changes', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onIncludeOrphanedChange = vi.fn();
    useSystemLogs.mockReturnValue({ ...baseHookValue, onIncludeOrphanedChange });

    renderPage();

    const toggle = screen.getByRole('checkbox', {
      name: /show entries with no linked application/i,
    });
    expect(toggle).not.toBeChecked();

    fireEvent.click(toggle);
    expect(onIncludeOrphanedChange).toHaveBeenCalledWith(true);
  });

  it('shows the error state when the list fetch fails', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useSystemLogs.mockReturnValue({ ...baseHookValue, error: 'Network error' });

    renderPage();

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it('opens the detail panel when a row is selected and closes it again', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onSelect = vi.fn();
    const onCloseDetail = vi.fn();
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 101,
      detail: makeRow(),
      onSelect,
      onCloseDetail,
    });

    renderPage();

    expect(screen.getByText(/entry #101/i)).toBeInTheDocument();
    expect(screen.getByText(/"missing_document_types"/)).toBeInTheDocument();
    expect(screen.getByText('SUBMITTED → NEEDS_DOCUMENTS')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /close details/i }));
    expect(onCloseDetail).toHaveBeenCalled();
  });

  it('paginates between pages when more than one page of results exists', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onGoToPage = vi.fn();
    useSystemLogs.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 120,
      pageCount: 3,
      currentPage: 1,
      onGoToPage,
    });

    renderPage();

    expect(screen.getByText(/page 2 of 3/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /next page/i }));
    expect(onGoToPage).toHaveBeenCalledWith(2);

    fireEvent.click(screen.getByRole('button', { name: /previous page/i }));
    expect(onGoToPage).toHaveBeenCalledWith(0);
  });
});
