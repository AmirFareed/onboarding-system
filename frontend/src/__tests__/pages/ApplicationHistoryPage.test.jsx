import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ApplicationHistoryPage from '../../pages/ApplicationHistory/ApplicationHistoryPage';

const { useApplicationHistory, useAuth } = vi.hoisted(() => ({
  useApplicationHistory: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/useApplicationHistory', () => ({ useApplicationHistory }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));

const baseHookValue = {
  rows: [],
  total: 0,
  loading: false,
  error: null,
  query: '',
  status: '',
  pageCount: 1,
  currentPage: 0,
  selectedId: null,
  timeline: null,
  timelineLoading: false,
  timelineError: null,
  onQueryChange: vi.fn(),
  onStatusChange: vi.fn(),
  onGoToPage: vi.fn(),
  onSelect: vi.fn(),
  onCloseTimeline: vi.fn(),
  onRefresh: vi.fn(),
};

function makeRow(overrides = {}) {
  return {
    application_id: 42,
    application_name: 'TMA Khal',
    status: 'PENDING_REVIEW',
    submitted_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-03T00:00:00Z',
    created_by: 'operator1',
    last_event_type: 'DOCUMENTS_RECEIVED',
    last_event_at: '2026-08-03T00:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  return render(<ApplicationHistoryPage />);
}

describe('ApplicationHistoryPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when no applications exist', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no applications found/i)).toBeInTheDocument();
  });

  it('renders a row with status and last event for each application', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
    });

    renderPage();

    expect(screen.getByText(/#42/i)).toBeInTheDocument();
    expect(screen.getByText('TMA Khal')).toBeInTheDocument();
    expect(screen.getAllByText(/under review/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/documents received/i)).toBeInTheDocument();
    expect(screen.getByText(/1 application/i)).toBeInTheDocument();
  });

  it('shows the access-denied state for a non-IT user', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useApplicationHistory.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /refresh/i })).not.toBeInTheDocument();
  });

  it('allows the Employee (development all-access) user to view the page', () => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
    useApplicationHistory.mockReturnValue(baseHookValue);

    renderPage();

    // Employee should see the empty state rather than access denied
    expect(screen.getByText(/no applications found/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /refresh/i })).toBeInTheDocument();
  });

  it('opens the timeline panel when a row is selected and closes it again', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onSelect = vi.fn();
    const onCloseTimeline = vi.fn();
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 42,
      timeline: {
        application_id: 42,
        application_name: 'TMA Khal',
        status: 'PENDING_REVIEW',
        submitted_at: '2026-08-01T00:00:00Z',
        created_by: 'operator1',
        events: [
          { kind: 'APPLICATION_CREATED', label: 'Application created', timestamp: '2026-08-01T00:00:00Z', actor_name: 'operator1' },
          { kind: 'REVIEW_DECISION', label: 'Application approved', timestamp: '2026-08-04T00:00:00Z', actor_name: 'reviewer1' },
        ],
      },
      onSelect,
      onCloseTimeline,
    });

    renderPage();

    expect(screen.getByText('Application created')).toBeInTheDocument();
    expect(screen.getByText('Application approved')).toBeInTheDocument();
    expect(screen.getByText('operator1')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /close timeline/i }));
    expect(onCloseTimeline).toHaveBeenCalled();
  });

  it('groups consecutive document uploads into a single expandable event', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 42,
      timeline: {
        application_id: 42,
        application_name: 'TMA Khal',
        status: 'PENDING_REVIEW',
        submitted_at: '2026-08-01T00:00:00Z',
        created_by: 'operator1',
        events: [
          { kind: 'APPLICATION_CREATED', label: 'Application created', timestamp: '2026-08-01T00:00:00Z', actor_name: 'operator1' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:00:00Z', document_type: 'ACCOUNT_MAINTENANCE_CERTIFICATE', copy_number: 1, filename: 'acct.pdf' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:01:00Z', document_type: 'ONE_LINK_LETTER', copy_number: 1, filename: 'one.pdf' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:02:00Z', document_type: 'ONE_LINK_LETTER', copy_number: 2, filename: 'one-copy2.pdf' },
          { kind: 'REVIEW_DECISION', label: 'Application approved', timestamp: '2026-08-02T00:00:00Z', actor_name: 'reviewer1' },
        ],
      },
    });

    renderPage();

    // The grouped header should appear once
    expect(screen.getByText(/Documents submitted/i)).toBeInTheDocument();
    // The summary shows the number of documents
    expect(screen.getByText(/3 documents/i)).toBeInTheDocument();

    // Expand and check human-readable document labels/details are present
    const summary = screen.getByText(/3 documents/i);
    fireEvent.click(summary);

    expect(screen.getByText(/Account Maintenance Certificate/i)).toBeInTheDocument();
    expect(screen.getByText(/acct.pdf/i)).toBeInTheDocument();

    // Other non-upload events remain visible
    expect(screen.getByText(/Application created/i)).toBeInTheDocument();
    expect(screen.getByText(/Application approved/i)).toBeInTheDocument();
  });

  it('triggers a search when the user submits the query', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    const onQueryChange = vi.fn();
    useApplicationHistory.mockReturnValue({ ...baseHookValue, onQueryChange });

    renderPage();

    fireEvent.change(screen.getByLabelText(/search application history/i), {
      target: { value: 'TMA' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^search$/i }));

    expect(onQueryChange).toHaveBeenCalledWith('TMA');
  });

  it('shows the error state when the list fetch fails', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({ ...baseHookValue, error: 'Network error' });

    renderPage();

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it('displays no cycle section when application has no resubmission requests', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 42,
      timeline: {
        application_id: 42,
        application_name: 'Direct Application',
        status: 'APPROVED',
        submitted_at: '2026-08-01T00:00:00Z',
        created_by: 'operator1',
        events: [
          { kind: 'APPLICATION_CREATED', label: 'Application created', timestamp: '2026-08-01T00:00:00Z', actor_name: 'operator1' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:00:00Z', document_type: 'ACCOUNT_MAINTENANCE_CERTIFICATE', copy_number: 1, filename: 'acct.pdf' },
          { kind: 'SUBMITTED_FOR_PROCESSING', label: 'Submitted for processing', timestamp: '2026-08-01T02:00:00Z', actor_name: 'operator1' },
          { kind: 'REVIEW_DECISION', label: 'Application approved', timestamp: '2026-08-02T00:00:00Z', actor_name: 'reviewer1' },
        ],
      },
    });

    renderPage();

    // Should NOT display any cycle heading
    expect(screen.queryByText(/Resubmission Cycle/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Cycle 1/i)).not.toBeInTheDocument();
  });

  it('displays one completed resubmission cycle (requested → received)', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 42,
      timeline: {
        application_id: 42,
        application_name: 'GDC Madyan',
        status: 'APPROVED',
        submitted_at: '2026-08-01T00:00:00Z',
        created_by: 'operator1',
        events: [
          { kind: 'APPLICATION_CREATED', label: 'Application created', timestamp: '2026-08-01T00:00:00Z', actor_name: 'operator1' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:00:00Z', document_type: 'ACCOUNT_MAINTENANCE_CERTIFICATE', copy_number: 1, filename: 'acct.pdf' },
          { kind: 'DOCUMENTS_REQUESTED', label: 'Missing documents requested from applicant', timestamp: '2026-08-01T07:00:00Z', actor_name: 'Verification Officer', actor_role: 'REVIEWER', detail: 'Requested: TRIPARTITE_AGREEMENT, AUTHORITY_LETTER' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-02T10:00:00Z', document_type: 'TRIPARTITE_AGREEMENT', copy_number: 1, filename: 'tripartite.pdf' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-02T10:01:00Z', document_type: 'AUTHORITY_LETTER', copy_number: 1, filename: 'authority.pdf' },
          { kind: 'DOCUMENTS_RECEIVED', label: 'Documents received', timestamp: '2026-08-02T10:15:00Z', actor_name: 'Employee', actor_role: 'EMPLOYEE' },
          { kind: 'SUBMITTED_FOR_PROCESSING', label: 'Submitted for processing', timestamp: '2026-08-02T11:00:00Z', actor_name: 'operator1' },
          { kind: 'REVIEW_DECISION', label: 'Application approved', timestamp: '2026-08-03T00:00:00Z', actor_name: 'reviewer1' },
        ],
      },
    });

    renderPage();

    // Should display cycle heading
    expect(screen.getByText(/Resubmission Cycle 1/i)).toBeInTheDocument();
    
    // Should show that documents were requested
    expect(screen.getByText(/Documents requested/i)).toBeInTheDocument();
    
    // Should show missing documents
    expect(screen.getByText(/Tripartite Agreement/i)).toBeInTheDocument();
    expect(screen.getByText(/Authority Letter/i)).toBeInTheDocument();
    
    // Should show resubmitted documents
    expect(screen.getByText(/Documents resubmitted/i)).toBeInTheDocument();
  });

  it('displays two resubmission cycles', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 42,
      timeline: {
        application_id: 42,
        application_name: 'GDC Madyan',
        status: 'APPROVED',
        submitted_at: '2026-08-01T00:00:00Z',
        created_by: 'operator1',
        events: [
          { kind: 'APPLICATION_CREATED', label: 'Application created', timestamp: '2026-08-01T00:00:00Z', actor_name: 'operator1' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:00:00Z', document_type: 'ACCOUNT_MAINTENANCE_CERTIFICATE', copy_number: 1, filename: 'acct.pdf' },
          
          // Cycle 1
          { kind: 'DOCUMENTS_REQUESTED', label: 'Missing documents requested from applicant', timestamp: '2026-08-01T07:00:00Z', actor_name: 'Verification Officer', actor_role: 'REVIEWER', detail: 'Requested: TRIPARTITE_AGREEMENT' },
          { kind: 'DOCUMENTS_RECEIVED', label: 'Documents received', timestamp: '2026-08-02T10:00:00Z', actor_name: 'Employee', actor_role: 'EMPLOYEE' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-02T10:00:00Z', document_type: 'TRIPARTITE_AGREEMENT', copy_number: 1, filename: 'tripartite.pdf' },
          
          // Cycle 2
          { kind: 'DOCUMENTS_REQUESTED', label: 'Missing documents requested from applicant', timestamp: '2026-08-02T11:00:00Z', actor_name: 'Verification Officer', actor_role: 'REVIEWER', detail: 'Requested: AUTHORITY_LETTER' },
          { kind: 'DOCUMENTS_RECEIVED', label: 'Documents received', timestamp: '2026-08-03T09:00:00Z', actor_name: 'Employee', actor_role: 'EMPLOYEE' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-03T09:00:00Z', document_type: 'AUTHORITY_LETTER', copy_number: 1, filename: 'authority.pdf' },
          
          { kind: 'SUBMITTED_FOR_PROCESSING', label: 'Submitted for processing', timestamp: '2026-08-03T10:00:00Z', actor_name: 'operator1' },
          { kind: 'REVIEW_DECISION', label: 'Application approved', timestamp: '2026-08-04T00:00:00Z', actor_name: 'reviewer1' },
        ],
      },
    });

    renderPage();

    // Should display both cycles
    expect(screen.getByText(/Resubmission Cycle 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Resubmission Cycle 2/i)).toBeInTheDocument();
  });

  it('displays an open resubmission cycle when request has no matching receipt', () => {
    useAuth.mockReturnValue({ user: { role: 'IT' } });
    useApplicationHistory.mockReturnValue({
      ...baseHookValue,
      rows: [makeRow()],
      total: 1,
      selectedId: 42,
      timeline: {
        application_id: 42,
        application_name: 'GDC Madyan',
        status: 'NEEDS_DOCUMENTS',
        submitted_at: '2026-08-01T00:00:00Z',
        created_by: 'operator1',
        events: [
          { kind: 'APPLICATION_CREATED', label: 'Application created', timestamp: '2026-08-01T00:00:00Z', actor_name: 'operator1' },
          { kind: 'DOCUMENT_UPLOADED', label: 'Document uploaded', timestamp: '2026-08-01T01:00:00Z', document_type: 'ACCOUNT_MAINTENANCE_CERTIFICATE', copy_number: 1, filename: 'acct.pdf' },
          { kind: 'DOCUMENTS_REQUESTED', label: 'Missing documents requested from applicant', timestamp: '2026-08-01T07:00:00Z', actor_name: 'Verification Officer', actor_role: 'REVIEWER', detail: 'Requested: TRIPARTITE_AGREEMENT' },
        ],
      },
    });

    renderPage();

    // Should display open cycle
    expect(screen.getByText(/Waiting for documents/i)).toBeInTheDocument();
    
    // Should show missing documents
    expect(screen.getByText(/Tripartite Agreement/i)).toBeInTheDocument();
    
    // Should indicate it's still waiting (no receipt date)
    expect(screen.queryByText(/Documents resubmitted/i)).not.toBeInTheDocument();
  });
});
