import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ValidationQueueDetailPanel from '../../../components/validationQueue/ValidationQueueDetailPanel/ValidationQueueDetailPanel';

const BASE_PROPS = {
  history: [],
  historyLoading: false,
  historyError: null,
  canOperate: true,
  actionLoading: false,
  actionError: null,
  onRequestDocuments: vi.fn(),
  onReject: vi.fn(),
  onSubmit: vi.fn(),
};

function makeApplication(overrides = {}) {
  return {
    application_id: 1,
    application_name: 'Test Application',
    status: 'SUBMITTED',
    received_document_count: 1,
    required_document_count: 2,
    completion_percentage: 50,
    missing_documents: ['ONE_LINK_LETTER'],
    required_documents: [
      { document_type: 'AUTHORITY_LETTER', is_present: true, copy_count: 1 },
      { document_type: 'ONE_LINK_LETTER', is_present: false, copy_count: 0 },
    ],
    ...overrides,
  };
}

// docs/TEAMMATE_BUG_TRIAGE.md-adjacent finding, 2026-08-23: this panel used
// to keep its own hardcoded ALL_REQUIRED_DOCUMENT_TYPES list (drifted out of
// sync with the real backend required set -- still had the already-removed
// SCHEDULE_OF_CHARGES). Because getDocumentTypeConfig() falls back to the
// catalogue's first entry (Authority Letter) for an unrecognized type, that
// stale entry rendered as a ghost, permanently-"Received" second "Authority
// Letter" row -- appearing to show Authority Letter in both the Received and
// Missing sections at once, even before a real Authority Letter existed.
// The fix sources the checklist entirely from `application.required_documents`
// (the same per-type list the backend completeness report already computes),
// so there is no longer any frontend-side list that can drift.
describe('ValidationQueueDetailPanel', () => {
  it('never shows the same required document as both received and missing', () => {
    render(
      <ValidationQueueDetailPanel
        {...BASE_PROPS}
        application={makeApplication({
          missing_documents: ['AUTHORITY_LETTER'],
          required_documents: [
            { document_type: 'AUTHORITY_LETTER', is_present: false, copy_count: 0 },
            { document_type: 'ONE_LINK_LETTER', is_present: true, copy_count: 3 },
          ],
        })}
      />
    );

    // Exactly one "Authority Letter" on the page: in Missing, not also in
    // Received (the ghost-row bug would have shown it twice).
    expect(screen.getAllByText('Authority Letter')).toHaveLength(1);
    const missingGroup = screen.getByText('Missing').closest('div');
    expect(within(missingGroup).getByText('Authority Letter')).toBeInTheDocument();
  });

  it('renders the Received list strictly from required_documents, with no extra entries', () => {
    render(
      <ValidationQueueDetailPanel
        {...BASE_PROPS}
        application={makeApplication()}
      />
    );

    const receivedGroup = screen.getByText('Received', { selector: 'p' }).closest('div');
    // Only the one is_present:true entry passed in -- no leftover/ghost row
    // from a hardcoded list the component no longer has.
    expect(within(receivedGroup).getAllByRole('listitem')).toHaveLength(1);
    expect(within(receivedGroup).getByText('Authority Letter')).toBeInTheDocument();
  });

  it('shows nothing as received when required_documents is empty', () => {
    render(
      <ValidationQueueDetailPanel
        {...BASE_PROPS}
        application={makeApplication({ required_documents: [] })}
      />
    );

    expect(screen.queryByText('Received')).not.toBeInTheDocument();
  });
});
