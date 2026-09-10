/**
 * Tests for useProcessingProgress's polling gate -- mirrors
 * useProcessingOverview.js's own `hasWork` gate (docs/TEAMMATE_BUG_TRIAGE.md's
 * corrected Medium #11: this hook polled unconditionally every 2.5s whenever
 * the autoRefreshProcessingStatus preference was on, with no check for
 * whether there was actually any queued/in-flight work left).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { useProcessingProgress } from './useProcessingProgress';

const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));

vi.mock('../services/processing', () => ({
  getProcessingProgress: vi.fn(),
  getProcessingDocuments: vi.fn(),
  retryProcessing: vi.fn(),
  startProcessing: vi.fn(),
}));
vi.mock('../utils/apiError', () => ({
  getApiErrorMessage: vi.fn((err) => err?.message ?? 'error'),
}));
vi.mock('../hooks/useAuth', () => ({ useAuth }));
vi.mock('../utils/preferences', () => ({
  getPreference: vi.fn(() => true),
}));

import { getProcessingDocuments, getProcessingProgress } from '../services/processing';

const IDLE_PROGRESS = { total_documents: 3, queued: 0, processing: 0, completed: 3 };
const ACTIVE_PROGRESS = { total_documents: 3, queued: 1, processing: 1, completed: 1 };

function wrapper({ children }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { role: 'Verification Officer' } });
  getProcessingDocuments.mockResolvedValue({ documents: [] });
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useProcessingProgress — hasWork-gated polling', () => {
  it('does not poll again once every document is complete (hasWork false)', async () => {
    getProcessingProgress.mockResolvedValue(IDLE_PROGRESS);

    renderHook(() => useProcessingProgress(42), { wrapper });

    // Flush the mount-effect's reload() microtask chain.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getProcessingProgress).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    // No further polling once there's nothing queued or processing.
    expect(getProcessingProgress).toHaveBeenCalledTimes(1);
  });

  it('keeps polling every 2.5s while there is queued or processing work', async () => {
    getProcessingProgress.mockResolvedValue(ACTIVE_PROGRESS);

    renderHook(() => useProcessingProgress(42), { wrapper });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getProcessingProgress).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(getProcessingProgress).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    expect(getProcessingProgress).toHaveBeenCalledTimes(3);
  });
});
