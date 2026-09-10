import { describe, it, expect } from 'vitest';
import { DOCUMENT_STATUSES } from './statuses';

describe('DOCUMENT_STATUSES', () => {
  it('should have unique labels for each primary document status', () => {
    const uploadedStatus = DOCUMENT_STATUSES.find((s) => s.value === 'UPLOADED');
    const pendingStatus = DOCUMENT_STATUSES.find((s) => s.value === 'PENDING');
    const completedStatus = DOCUMENT_STATUSES.find((s) => s.value === 'COMPLETED');

    expect(uploadedStatus.label).toBe('Uploaded');
    expect(pendingStatus.label).toBe('Pending');
    expect(completedStatus.label).toBe('Completed');

    // Ensure all labels are correctly differentiated
    expect(uploadedStatus.label).not.toBe(pendingStatus.label);
    expect(uploadedStatus.label).not.toBe(completedStatus.label);
    expect(pendingStatus.label).not.toBe(completedStatus.label);
  });
});
