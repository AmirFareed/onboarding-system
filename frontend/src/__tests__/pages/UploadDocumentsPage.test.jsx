import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import UploadDocumentsPage from '../../pages/UploadDocuments/UploadDocumentsPage';

const { useDocuments, useToast } = vi.hoisted(() => ({
  useDocuments: vi.fn(),
  useToast: vi.fn(),
}));

vi.mock('../../hooks/useDocuments', () => ({ useDocuments }));
vi.mock('../../components/common/Toast/ToastContext', () => ({ useToast }));
vi.mock('../../utils/preferences', () => ({
  getPreference: vi.fn(() => true),
}));
vi.mock('../../services/processing', () => ({
  startProcessing: vi.fn(() => Promise.resolve()),
}));

const BASE_HOOK_VALUE = {
  documents: [],
  loading: false,
  error: null,
  reload: vi.fn(),
  pending: {},
  uploadBulk: vi.fn(),
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/applications/1/upload']}>
      <Routes>
        <Route path="/applications/:applicationId/upload" element={<UploadDocumentsPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('UploadDocumentsPage', () => {
  it('shows the bulk PDF dropzone when no bulk upload has been attempted', () => {
    useDocuments.mockReturnValue({ ...BASE_HOOK_VALUE, documents: [] });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.getByText('Upload Combined PDF')).toBeInTheDocument();
  });

  it('shows the processing banner while a bulk upload is still being split', () => {
    useDocuments.mockReturnValue({
      ...BASE_HOOK_VALUE,
      documents: [
        { id: 1, document_type: 'BULK_UPLOAD', processing_status: 'UPLOADED' },
      ],
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(
      screen.getByText(/being split and analyzed in the background/i)
    ).toBeInTheDocument();
    expect(screen.queryByText('Upload Combined PDF')).not.toBeInTheDocument();
  });

  it('shows the dropzone again once a bulk upload has completed', () => {
    useDocuments.mockReturnValue({
      ...BASE_HOOK_VALUE,
      documents: [
        { id: 1, document_type: 'BULK_UPLOAD', processing_status: 'COMPLETED' },
      ],
    });
    useToast.mockReturnValue({ success: vi.fn(), error: vi.fn() });

    renderPage();

    expect(screen.getByText('Upload Combined PDF')).toBeInTheDocument();
  });
});
