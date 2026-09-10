/**
 * Tests for useProcessingOverview's loading flag (docs/TEAMMATE_BUG_TRIAGE.md's
 * Medium #8: `reload()` set `loading` to false as its very first line, before
 * the `await listApplications(...)` below it -- so `loading && rows.length === 0`
 * in ProcessingPage.jsx briefly rendered the empty state before real data
 * ever arrived).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useProcessingOverview } from './useProcessingOverview';

vi.mock('../services/applications', () => ({
  listApplications: vi.fn(),
}));
vi.mock('../services/processing', () => ({
  getProcessingProgress: vi.fn(),
  retryProcessing: vi.fn(),
}));
vi.mock('../utils/apiError', () => ({
  getApiErrorMessage: vi.fn((err) => err?.message ?? 'error'),
}));
vi.mock('../utils/preferences', () => ({
  getPreference: vi.fn(() => false),
}));

import { listApplications } from '../services/applications';
import { getProcessingProgress } from '../services/processing';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useProcessingOverview — loading flag', () => {
  it('stays true until the initial fetch resolves, never flips false early', async () => {
    let resolveList;
    listApplications.mockReturnValue(
      new Promise((resolve) => {
        resolveList = resolve;
      })
    );
    getProcessingProgress.mockResolvedValue(null);

    const { result } = renderHook(() => useProcessingOverview());

    expect(result.current.loading).toBe(true);

    // Still loading while the request is in flight -- this is the exact
    // window where the old code prematurely flipped `loading` to false.
    expect(result.current.loading).toBe(true);

    await act(async () => {
      resolveList({ items: [{ id: 1 }] });
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.rows).toHaveLength(1);
  });
});
