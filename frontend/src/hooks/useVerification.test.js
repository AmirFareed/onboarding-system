/**
 * Tests for useVerification — focused on the stale-response request guard.
 *
 * The guard (activeAppId ref) must discard any fetch response that arrives
 * after the hook's applicationId has already changed to a different value.
 *
 * The hook does not expose raw internal state (validationResults), so tests
 * observe the derived public surface: overallStatus (derived from rules),
 * completeness, loading, and error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useVerification } from './useVerification';

vi.mock('../services/documents', () => ({
  listDocuments: vi.fn(),
}));
vi.mock('../services/verification', () => ({
  getValidationResults: vi.fn(),
  getCompleteness: vi.fn(),
}));
vi.mock('../utils/apiError', () => ({
  getApiErrorMessage: vi.fn((err) => err?.message ?? 'error'),
}));

import { listDocuments } from '../services/documents';
import { getValidationResults, getCompleteness } from '../services/verification';

// Helper: build a deferred promise whose resolve/reject can be called externally.
function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// App A has a PASS rule → overallStatus derives to 'VERIFIED'.
const APP_A_RESULTS = { results: [{ id: 'rule-a', status: 'PASS', rule_category: 'format', related_document_ids: [] }] };
const APP_A_COMPLETENESS = { completion_percentage: 50, required_documents: [] };
const APP_A_DOCUMENTS = { items: [] };

// App B has a FAIL rule → overallStatus derives to 'FAILED'.
const APP_B_RESULTS = { results: [{ id: 'rule-b', status: 'FAIL', rule_category: 'format', related_document_ids: [] }] };
const APP_B_COMPLETENESS = { completion_percentage: 100, required_documents: [] };
const APP_B_DOCUMENTS = { items: [] };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useVerification — stale-response guard', () => {
  it('discards App A response when it resolves after App B has already loaded', async () => {
    // App A's fetch is deferred — will resolve late.
    const aValidation = deferred();
    const aCompleteness = deferred();
    const aDocuments = deferred();

    // App B's fetches are also deferred — resolved in controlled order below.
    const bValidation = deferred();
    const bCompleteness = deferred();
    const bDocuments = deferred();

    getValidationResults
      .mockReturnValueOnce(aValidation.promise)  // App A (first call)
      .mockReturnValueOnce(bValidation.promise); // App B (second call)
    getCompleteness
      .mockReturnValueOnce(aCompleteness.promise)
      .mockReturnValueOnce(bCompleteness.promise);
    listDocuments
      .mockReturnValueOnce(aDocuments.promise)
      .mockReturnValueOnce(bDocuments.promise);

    const { result, rerender } = renderHook(
      ({ appId }) => useVerification(appId),
      { initialProps: { appId: 1 } }
    );

    // App A's fetches are inflight — hook is loading.
    expect(result.current.loading).toBe(true);

    // Simulate fast navigation to App B before App A resolves.
    rerender({ appId: 2 });

    // Resolve App B's fetches — this is the "current" app.
    await act(async () => {
      bValidation.resolve(APP_B_RESULTS);
      bCompleteness.resolve(APP_B_COMPLETENESS);
      bDocuments.resolve(APP_B_DOCUMENTS);
    });

    // Wait for App B's state to settle.
    await waitFor(() => expect(result.current.loading).toBe(false));

    // App B's data: FAIL rule → overallStatus = 'FAILED'.
    expect(result.current.overallStatus).toBe('FAILED');
    // App B's completeness is 100%.
    expect(result.current.completeness?.completion_percentage).toBe(100);

    // Now resolve App A's stale fetch — it arrives late, after B is rendered.
    // If the guard is broken, A's PASS rule would flip overallStatus to 'VERIFIED'.
    await act(async () => {
      aValidation.resolve(APP_A_RESULTS);
      aCompleteness.resolve(APP_A_COMPLETENESS);
      aDocuments.resolve(APP_A_DOCUMENTS);
    });

    // State must still reflect App B — A's stale response was discarded.
    expect(result.current.overallStatus).toBe('FAILED');
    expect(result.current.completeness?.completion_percentage).toBe(100);
    // Loading must remain false — A's stale finally-block must not flip it.
    expect(result.current.loading).toBe(false);
  });

  it('discards stale error — navigating away before a failing fetch resolves', async () => {
    const aValidation = deferred();
    const bValidation = deferred();
    const bCompleteness = deferred();
    const bDocuments = deferred();

    getValidationResults
      .mockReturnValueOnce(aValidation.promise)
      .mockReturnValueOnce(bValidation.promise);
    getCompleteness
      .mockReturnValueOnce(Promise.resolve(APP_A_COMPLETENESS))
      .mockReturnValueOnce(bCompleteness.promise);
    listDocuments
      .mockReturnValueOnce(Promise.resolve(APP_A_DOCUMENTS))
      .mockReturnValueOnce(bDocuments.promise);

    const { result, rerender } = renderHook(
      ({ appId }) => useVerification(appId),
      { initialProps: { appId: 1 } }
    );

    // Navigate away before App A's validation fetch finishes.
    rerender({ appId: 2 });

    // Resolve App B cleanly.
    await act(async () => {
      bValidation.resolve(APP_B_RESULTS);
      bCompleteness.resolve(APP_B_COMPLETENESS);
      bDocuments.resolve(APP_B_DOCUMENTS);
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();

    // Reject App A's stale validation fetch with a network error.
    await act(async () => {
      aValidation.reject(new Error('Network error for App A'));
    });

    // Stale error must NOT overwrite the current null error state.
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });
});
