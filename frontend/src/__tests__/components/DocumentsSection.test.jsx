import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DocumentsSection from '../../components/documents/DocumentsSection/DocumentsSection';

const { useDocuments } = vi.hoisted(() => ({ useDocuments: vi.fn() }));
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock('../../hooks/useDocuments', () => ({ useDocuments }));
vi.mock('../../hooks/useAuth', () => ({ useAuth }));

function documentItem(overrides) {
  return {
    id: 1,
    application_id: 9,
    document_type: 'AUTHORITY_LETTER',
    copy_number: 1,
    processing_status: 'COMPLETED',
    original_filename: 'authority.pdf',
    storage_path: 'applications/APP-000009/required/authority.pdf',
    ...overrides,
  };
}

function renderSection() {
  return render(
    <MemoryRouter>
      <DocumentsSection applicationId={9} />
    </MemoryRouter>
  );
}

describe('DocumentsSection', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading state while documents are being fetched', () => {
    useDocuments.mockReturnValue({
      documents: [],
      loading: true,
      error: null,
      reload: vi.fn(),
    });

    renderSection();

    expect(screen.getByRole('region', { name: /documents/i })).toBeInTheDocument();
  });

  it('groups required documents under their catalogue heading', () => {
    useDocuments.mockReturnValue({
      documents: [documentItem({ id: 1 })],
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    renderSection();

    expect(screen.getByText('Authority Letter')).toBeInTheDocument();
    expect(screen.getByText('Copy 1')).toBeInTheDocument();
    expect(screen.getByText('authority.pdf')).toBeInTheDocument();
  });

  it('does not render a BULK_UPLOAD placeholder under any required heading', () => {
    useDocuments.mockReturnValue({
      documents: [
        documentItem({
          id: 99,
          document_type: 'BULK_UPLOAD',
          original_filename: 'Conservator Wildlife Peshawar Zoo.pdf',
        }),
      ],
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    renderSection();

    expect(screen.queryByText('Authority Letter')).not.toBeInTheDocument();
    expect(
      screen.queryByText('Conservator Wildlife Peshawar Zoo.pdf')
    ).not.toBeInTheDocument();
    expect(screen.getByText(/still being processed/i)).toBeInTheDocument();
  });

  it('shows the empty state when there are no documents', () => {
    useDocuments.mockReturnValue({
      documents: [],
      loading: false,
      error: null,
      reload: vi.fn(),
    });

    renderSection();

    expect(screen.getByText(/no documents uploaded yet/i)).toBeInTheDocument();
  });
});