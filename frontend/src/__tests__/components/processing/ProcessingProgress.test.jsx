import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ProcessingProgress from '../../../components/processing/ProcessingProgress/ProcessingProgress';
import { useProcessingProgress } from '../../../hooks/useProcessingProgress';

vi.mock('../../../hooks/useProcessingProgress', () => ({
  useProcessingProgress: vi.fn(),
}));

const BASE_PROGRESS = {
  total_documents: 1,
  completed: 0,
  queued: 0,
  processing: 0,
  documents_needing_attention: 0,
  progress_percentage: 0,
};

// docs/TEAMMATE_BUG_TRIAGE.md Low #24: `document.status.toLowerCase()` had no
// null guard, so a document with a missing/null status crashed the whole
// processing panel instead of just rendering without a status-specific class.
describe('ProcessingProgress', () => {
  it('does not throw when a document has a null status', () => {
    useProcessingProgress.mockReturnValue({
      progress: BASE_PROGRESS,
      documents: [{ document_id: 1, file_name: 'file.pdf', status: null, message: 'Unknown' }],
      loading: false,
      actionLoading: false,
      error: null,
      reload: vi.fn(),
      start: vi.fn(),
      retry: vi.fn(),
    });

    expect(() => render(<ProcessingProgress applicationId={1} />)).not.toThrow();
    expect(screen.getByText('file.pdf')).toBeInTheDocument();
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('still renders a real status normally', () => {
    useProcessingProgress.mockReturnValue({
      progress: BASE_PROGRESS,
      documents: [{ document_id: 1, file_name: 'file.pdf', status: 'COMPLETED', message: 'Processed successfully' }],
      loading: false,
      actionLoading: false,
      error: null,
      reload: vi.fn(),
      start: vi.fn(),
      retry: vi.fn(),
    });

    render(<ProcessingProgress applicationId={1} />);
    expect(screen.getByText('Processed successfully')).toBeInTheDocument();
  });
});
