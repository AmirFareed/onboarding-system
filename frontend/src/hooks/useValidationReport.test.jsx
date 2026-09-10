/**
 * Tests for useValidationReport's `loadApplications` -- focused on the
 * stale-response guard added to mirror useVerification.js's `reload`
 * (docs/TEAMMATE_BUG_TRIAGE.md's corrected Medium #14: the sibling `reload`
 * in this same file already had a request-ID guard (`reportRequestIdRef`),
 * but `loadApplications` had none at all).
 *
 * The guard here (`activeStatusFilter` ref, compared against a
 * locally-captured value before every setState) is the same shape as
 * useVerification.js's `activeAppId` guard: capture the in-flight request's
 * key, and discard the response if that key is no longer current by the
 * time it resolves.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { useValidationReport } from './useValidationReport';

vi.mock('../services/applications', () => ({
  listApplications: vi.fn(),
}));
vi.mock('../services/reports', () => ({
  getValidationReport: vi.fn(),
}));
vi.mock('../services/technicalValidation', () => ({
  getTechnicalValidation: vi.fn(),
}));
vi.mock('../services/analysis', () => ({
  getAnalysisResults: vi.fn(),
}));
vi.mock('../services/normalization', () => ({
  getNormalizedFields: vi.fn(),
}));
vi.mock('../services/verification', () => ({
  getCompleteness: vi.fn(),
  getValidationResults: vi.fn(),
}));
vi.mock('../utils/apiError', () => ({
  getApiErrorMessage: vi.fn((err) => err?.message ?? 'error'),
}));

import { listApplications } from '../services/applications';

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const PENDING_ITEMS = { items: [{ id: 1, status: 'PENDING_REVIEW' }], total: 1 };
const APPROVED_ITEMS = { items: [{ id: 2, status: 'APPROVED' }], total: 1 };

function wrapper({ children }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useValidationReport — loadApplications stale-response guard', () => {
  it('discards a stale PENDING_REVIEW response that resolves after switching to APPROVED', async () => {
    const pending = deferred();
    const approved = deferred();

    listApplications
      .mockReturnValueOnce(pending.promise) // initial mount fetch (PENDING_REVIEW)
      .mockReturnValueOnce(approved.promise); // after onStatusChange('APPROVED')

    const { result } = renderHook(() => useValidationReport(), { wrapper });

    expect(result.current.appsLoading).toBe(true);

    // Switch the filter before the first (PENDING_REVIEW) fetch resolves.
    act(() => {
      result.current.onStatusChange('APPROVED');
    });

    // Resolve the newer (APPROVED) request first.
    await act(async () => {
      approved.resolve(APPROVED_ITEMS);
    });
    await waitFor(() => expect(result.current.appsLoading).toBe(false));
    expect(result.current.applications).toEqual(APPROVED_ITEMS.items);

    // Now the stale PENDING_REVIEW request resolves late.
    await act(async () => {
      pending.resolve(PENDING_ITEMS);
    });

    // Must still reflect APPROVED -- the stale response was discarded.
    expect(result.current.applications).toEqual(APPROVED_ITEMS.items);
    expect(result.current.appsLoading).toBe(false);
  });

  it('discards a stale error from the older request', async () => {
    const pending = deferred();
    const approved = deferred();

    listApplications
      .mockReturnValueOnce(pending.promise)
      .mockReturnValueOnce(approved.promise);

    const { result } = renderHook(() => useValidationReport(), { wrapper });

    act(() => {
      result.current.onStatusChange('APPROVED');
    });

    await act(async () => {
      approved.resolve(APPROVED_ITEMS);
    });
    await waitFor(() => expect(result.current.appsLoading).toBe(false));
    expect(result.current.appsError).toBeNull();

    await act(async () => {
      pending.reject(new Error('stale network error'));
    });

    expect(result.current.appsError).toBeNull();
    expect(result.current.applications).toEqual(APPROVED_ITEMS.items);
  });
});
