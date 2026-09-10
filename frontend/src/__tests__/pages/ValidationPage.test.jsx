import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ValidationPage from '../../pages/Validation/ValidationPage';

const { useValidationQueue, useAuth, useToast } = vi.hoisted(() => ({
  useValidationQueue: vi.fn(),
  useAuth: vi.fn(),
  useToast: vi.fn(),
}));

vi.mock('../../hooks/useValidationQueue', () => ({ useValidationQueue }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));
vi.mock('../../components/common/Toast/ToastContext', () => ({ useToast }));

const baseHookValue = {
  applications: [],
  total: 0,
  loading: false,
  error: null,
  selectedId: null,
  onSelect: vi.fn(),
  selectedApplication: null,
  history: [],
  historyLoading: false,
  historyError: null,
  actionLoading: false,
  actionError: null,
  onRequestDocuments: vi.fn(),
  onReject: vi.fn(),
  onSubmit: vi.fn(),
  onRefresh: vi.fn(),
};

// Mirrors backend/app/completeness/constants.py::REQUIRED_DOCUMENT_TYPES (7
// real required types -- kept in sync manually here since this is a plain
// JS test fixture, not a shared import from the backend).
const REQUIRED_TYPES = [
  'TRIPARTITE_AGREEMENT',
  'BILATERAL_AGREEMENT',
  'ACCOUNT_MAINTENANCE_CERTIFICATE',
  'ONE_LINK_LETTER',
  'AUTHORITY_LETTER',
  'BUSINESS_REQUIREMENT_DOCUMENT',
  'FORMAL_REQUEST_LETTER',
];

function makeApplication(overrides = {}) {
  const missingDocuments =
    overrides.missing_documents ?? ['ONE_LINK_LETTER', 'TRIPARTITE_AGREEMENT', 'AUTHORITY_LETTER'];
  return {
    application_id: 42,
    application_name: 'TMA Khal',
    status: 'SUBMITTED',
    submitted_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z',
    created_by: 'operator1',
    required_document_count: 9,
    received_document_count: 6,
    missing_document_count: 3,
    missing_documents: missingDocuments,
    required_documents: REQUIRED_TYPES.map((type) => ({
      document_type: type,
      is_present: !missingDocuments.includes(type),
      copy_count: missingDocuments.includes(type) ? 0 : 1,
    })),
    completion_percentage: 66.67,
    needs_attention: true,
    last_event_type: 'DOCUMENTS_REQUESTED',
    last_event_at: '2026-08-02T00:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  return render(<ValidationPage />);
}

describe('ValidationPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows the empty state when the queue has no applications', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useToast.mockReturnValue({ success: vi.fn() });
    useValidationQueue.mockReturnValue(baseHookValue);

    renderPage();

    expect(screen.getByText(/no applications to validate/i)).toBeInTheDocument();
  });

  it('renders a row for each application in the queue', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useToast.mockReturnValue({ success: vi.fn() });
    useValidationQueue.mockReturnValue({
      ...baseHookValue,
      applications: [makeApplication()],
      total: 1,
    });

    renderPage();

    expect(screen.getByText(/TMA Khal/i)).toBeInTheDocument();
    expect(screen.getAllByText(/needs attention/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 application/i)).toBeInTheDocument();
  });

  it('shows the error state when the queue fetch fails', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useToast.mockReturnValue({ success: vi.fn() });
    useValidationQueue.mockReturnValue({ ...baseHookValue, error: 'Network error' });

    renderPage();

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it('shows operator actions for an OPERATOR user and hides them for other roles', () => {
    useToast.mockReturnValue({ success: vi.fn() });
    useValidationQueue.mockReturnValue({
      ...baseHookValue,
      applications: [makeApplication()],
      total: 1,
      selectedId: 42,
      selectedApplication: makeApplication(),
    });

    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    const operatorView = render(<ValidationPage />);
    expect(operatorView.getByRole('button', { name: /request documents/i })).toBeInTheDocument();
    expect(
      operatorView.getByRole('button', { name: /submit for processing/i })
    ).toBeInTheDocument();
    expect(operatorView.getByRole('button', { name: /reject application/i })).toBeInTheDocument();
    operatorView.unmount();

    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
    const employeeView = render(<ValidationPage />);
    expect(employeeView.queryByText(/view-only access/i)).not.toBeInTheDocument();
    expect(
      employeeView.getByRole('button', { name: /request documents/i })
    ).toBeInTheDocument();
    expect(
      employeeView.getByRole('button', { name: /reject application/i })
    ).toBeInTheDocument();
    employeeView.unmount();

    useAuth.mockReturnValue({ user: { role: 'REVIEWER' } });
    const reviewerView = render(<ValidationPage />);
    expect(
      reviewerView.getByText(/view-only access/i)
    ).toBeInTheDocument();
    expect(
      reviewerView.queryByRole('button', { name: /request documents/i })
    ).not.toBeInTheDocument();
  });

  it('pre-checks the application missing documents and sends the selection', async () => {
    const onRequestDocuments = vi.fn(() => Promise.resolve({ message: 'ok' }));
    const success = vi.fn();

    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useToast.mockReturnValue({ success });
    useValidationQueue.mockReturnValue({
      ...baseHookValue,
      applications: [makeApplication()],
      total: 1,
      selectedId: 42,
      selectedApplication: makeApplication(),
      onRequestDocuments,
    });

    renderPage();

    const oneLinkCheckbox = screen.getByRole('checkbox', {
      name: /1-link application form/i,
    });
    expect(oneLinkCheckbox).toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: /request documents/i }));

    await waitFor(() => {
      expect(onRequestDocuments).toHaveBeenCalledWith({
        missingDocumentTypes: ['ONE_LINK_LETTER', 'TRIPARTITE_AGREEMENT', 'AUTHORITY_LETTER'],
        reason: undefined,
      });
    });
    expect(success).toHaveBeenCalledWith(expect.stringMatching(/document request sent/i));
  });

  it('shows the summary counter cards for the queue', () => {
    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    useToast.mockReturnValue({ success: vi.fn() });
    useValidationQueue.mockReturnValue({
      ...baseHookValue,
      applications: [makeApplication()],
      total: 1,
    });

    renderPage();

    expect(screen.getByLabelText('Pending')).toHaveTextContent('0');
    expect(screen.getByLabelText('Needs attention')).toHaveTextContent('1');
    expect(screen.getByLabelText('Missing documents')).toHaveTextContent('0');
  });

  it('shows the received checklist and a complete state when no documents are missing', () => {
    useToast.mockReturnValue({ success: vi.fn() });
    useValidationQueue.mockReturnValue({
      ...baseHookValue,
      applications: [makeApplication({ missing_documents: [], missing_document_count: 0 })],
      total: 1,
      selectedId: 42,
      selectedApplication: makeApplication({
        missing_documents: [],
        missing_document_count: 0,
      }),
    });

    useAuth.mockReturnValue({ user: { role: 'OPERATOR' } });
    renderPage();

    expect(screen.getByText(/all required documents received/i)).toBeInTheDocument();
    expect(screen.getByText('Tripartite Agreement')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /request documents/i })).not.toBeInTheDocument();
  });
});