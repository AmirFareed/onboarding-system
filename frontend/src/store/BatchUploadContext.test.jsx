/**
 * Tests for the batch upload queue's persistence, file recovery and
 * reload-time reconciliation.
 *
 * Added after a real incident (2026-09-14): a 34-file batch lost all record
 * of its still-pending files the moment the browser/dev-server session
 * ended, because the queue previously lived only in React state with
 * nothing written anywhere else.
 *
 * Extended the same day after a follow-up report: recovering an item's
 * *record* on reload wasn't enough on its own -- the user (reasonably)
 * expected a reload/navigation to not interrupt the batch at all, not just
 * to remember that files were still queued. `batchFileStore` (IndexedDB,
 * mocked below) now recovers a queued file's actual bytes across a real
 * reload, and BatchUploadProvider auto-resumes on mount if the page loaded
 * with unfinished work -- see BatchUploadContext.jsx's STORAGE_KEY and
 * bootstrap-effect comments for the full writeup.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BatchUploadProvider, fileIsMissing, useBatchUploadStore } from './BatchUploadContext';
import { ApplicationsProvider } from './ApplicationsContext';

vi.mock('../services/applications', () => ({
  listApplications: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  createApplication: vi.fn(),
  getApplication: vi.fn(),
  deleteApplication: vi.fn(),
}));
vi.mock('../services/documents', () => ({
  listDocuments: vi.fn(() => Promise.resolve({ items: [] })),
  uploadBulkDocument: vi.fn(),
}));
vi.mock('../services/processing', () => ({
  startProcessing: vi.fn(),
  getProcessingProgress: vi.fn(() => Promise.resolve(null)),
}));
vi.mock('./batchFileStore', () => ({
  putFile: vi.fn(() => Promise.resolve()),
  getFile: vi.fn(() => Promise.resolve(null)),
  deleteFile: vi.fn(() => Promise.resolve()),
  clearAllFiles: vi.fn(() => Promise.resolve()),
}));

import { createApplication, getApplication } from '../services/applications';
import { uploadBulkDocument } from '../services/documents';
import { startProcessing } from '../services/processing';
import { putFile, getFile, deleteFile, clearAllFiles } from './batchFileStore';

const STORAGE_KEY = 'onboarding-system.batchUploadQueue.v1';

function wrapper({ children }) {
  return (
    <ApplicationsProvider>
      <BatchUploadProvider>{children}</BatchUploadProvider>
    </ApplicationsProvider>
  );
}

function makeFile(name) {
  return new File(['%PDF-1.7'], name, { type: 'application/pdf' });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  createApplication.mockResolvedValue({ ok: true });
  getApplication.mockResolvedValue({ id: 1, status: 'SUBMITTED', name: null });
  putFile.mockResolvedValue();
  getFile.mockResolvedValue(null);
  deleteFile.mockResolvedValue();
  clearAllFiles.mockResolvedValue();
});

afterEach(() => {
  window.localStorage.clear();
});

describe('fileIsMissing', () => {
  it('is true only for a pending item with no File object', () => {
    expect(fileIsMissing({ status: 'pending', file: null })).toBe(true);
    expect(fileIsMissing({ status: 'pending', file: makeFile('a.pdf') })).toBe(false);
    expect(fileIsMissing({ status: 'completed', file: null })).toBe(false);
    expect(fileIsMissing({ status: 'processing', file: null })).toBe(false);
  });
});

describe('BatchUploadContext persistence', () => {
  it('persists added files to localStorage without the File object itself', async () => {
    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    act(() => {
      result.current.addFiles([makeFile('TMA Example.pdf')]);
    });

    await waitFor(() => {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      expect(raw).not.toBeNull();
    });
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY));
    expect(stored).toHaveLength(1);
    expect(stored[0].filename).toBe('TMA Example.pdf');
    expect(stored[0].status).toBe('pending');
    expect(stored[0]).not.toHaveProperty('file');
  });

  it('also stores the file bytes in IndexedDB (via batchFileStore) so a real reload can recover them', async () => {
    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });
    const file = makeFile('TMA Example.pdf');

    act(() => {
      result.current.addFiles([file]);
    });

    await waitFor(() => {
      expect(putFile).toHaveBeenCalledWith(result.current.items[0].clientId, file);
    });
  });

  it('a fresh addFiles() clientId never collides with a restored one', async () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          clientId: 'batch-5',
          filename: 'Restored.pdf',
          previewName: 'Restored',
          status: 'pending',
          phase: null,
          progress: 0,
          applicationId: null,
          applicationName: null,
          applicationStatus: null,
          error: null,
        },
      ])
    );

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });
    // The restored pending item triggers the bootstrap effect's own
    // auto-resume attempt in the background (see the reload-time file
    // recovery tests below) -- let that fully settle (getFile is called
    // early, running flips back to false once its own start() cycle is
    // done) before adding more files, so its state updates don't land
    // outside of act() here.
    await waitFor(() => {
      expect(getFile).toHaveBeenCalledWith('batch-5');
    });
    await waitFor(() => {
      expect(result.current.running).toBe(false);
    });

    act(() => {
      result.current.addFiles([makeFile('New.pdf')]);
    });

    const clientIds = result.current.items.map((item) => item.clientId);
    expect(new Set(clientIds).size).toBe(clientIds.length);
  });

  it('removeFile() deletes the file from IndexedDB, and reset() clears all of them', async () => {
    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });
    act(() => {
      result.current.addFiles([makeFile('a.pdf'), makeFile('b.pdf')]);
    });
    await waitFor(() => expect(result.current.items).toHaveLength(2));

    const [first] = result.current.items;
    act(() => {
      result.current.removeFile(first.clientId);
    });
    expect(deleteFile).toHaveBeenCalledWith(first.clientId);

    act(() => {
      result.current.reset();
    });
    expect(clearAllFiles).toHaveBeenCalled();
  });
});

describe('BatchUploadContext reload-time file recovery', () => {
  function seedPendingItem(overrides = {}) {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          clientId: 'batch-1',
          filename: 'Old Session.pdf',
          previewName: 'Old Session',
          status: 'pending',
          phase: null,
          progress: 0,
          applicationId: null,
          applicationName: null,
          applicationStatus: null,
          error: null,
          ...overrides,
        },
      ])
    );
  }

  it('stays fileIsMissing when IndexedDB has nothing stored for it', async () => {
    seedPendingItem();

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].filename).toBe('Old Session.pdf');
    await waitFor(() => {
      expect(getFile).toHaveBeenCalledWith('batch-1');
    });
    expect(fileIsMissing(result.current.items[0])).toBe(true);
  });

  it('recovers the real file from IndexedDB on mount, clearing fileIsMissing', async () => {
    seedPendingItem();
    const recovered = makeFile('Old Session.pdf');
    getFile.mockResolvedValue(recovered);

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    await waitFor(() => {
      expect(fileIsMissing(result.current.items[0])).toBe(false);
    });
    expect(result.current.items[0].file).toBe(recovered);
  });

  it('auto-resumes processing on mount once a recovered file makes the queue runnable again', async () => {
    seedPendingItem();
    getFile.mockResolvedValue(makeFile('Old Session.pdf'));
    createApplication.mockResolvedValue({ id: 9, status: 'SUBMITTED', name: 'Old Session' });
    getApplication.mockResolvedValue({ id: 9, status: 'PENDING_REVIEW', name: 'Old Session' });
    uploadBulkDocument.mockResolvedValue({});
    startProcessing.mockResolvedValue({});

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    // Nobody calls start() in this test -- reaching 'completed' on its own
    // is the whole point: the batch should resume itself after a reload,
    // matching what a user navigating back (or reopening the tab) expects.
    await waitFor(() => {
      expect(result.current.items[0].status).toBe('completed');
    });
    expect(createApplication).toHaveBeenCalled();
    expect(uploadBulkDocument).toHaveBeenCalled();
  });
});

describe('BatchUploadContext reload-time reconciliation', () => {
  //: Every case here restores a 'processing' item with a real applicationId
  //: -- exactly the shape a file left mid-upload/mid-analysis has when the
  //: session ends, per the incident this whole feature exists for.
  function seedProcessingItem(overrides = {}) {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([
        {
          clientId: 'batch-1',
          filename: 'In Flight.pdf',
          previewName: 'In Flight',
          status: 'processing',
          phase: 'polling',
          progress: 40,
          applicationId: 7,
          applicationName: 'In Flight',
          applicationStatus: 'PROCESSING',
          error: null,
          ...overrides,
        },
      ])
    );
  }

  it('reconciles a restored item whose application had already finished successfully', async () => {
    seedProcessingItem();
    getApplication.mockResolvedValue({ id: 7, status: 'PENDING_REVIEW', name: 'In Flight' });

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    await waitFor(() => {
      expect(result.current.items[0].status).toBe('completed');
    });
  });

  it('reconciles a restored item whose application had failed processing', async () => {
    seedProcessingItem();
    getApplication.mockResolvedValue({ id: 7, status: 'PROCESSING_FAILED', name: 'In Flight' });

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    await waitFor(() => {
      expect(result.current.items[0].status).toBe('failed');
    });
  });

  it('marks the item failed with a clear reason when its application was deleted in the meantime', async () => {
    // The real incident: Clear History deleted the application this item
    // was still processing against.
    seedProcessingItem();
    getApplication.mockRejectedValue({
      response: { status: 404, data: { detail: 'Application not found' } },
    });

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    await waitFor(() => {
      expect(result.current.items[0].status).toBe('failed');
    });
    expect(result.current.items[0].error).toMatch(/deleted while the batch was running/i);
  });

  it('resets a restored item that never even got an applicationId to a re-addable pending row', async () => {
    seedProcessingItem({ applicationId: null, applicationStatus: null, phase: 'creating' });

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });

    await waitFor(() => {
      expect(result.current.items[0].status).toBe('pending');
    });
    expect(fileIsMissing(result.current.items[0])).toBe(true);
    expect(getApplication).not.toHaveBeenCalled();
  });

  it('auto-resume safely finds nothing to run when the only recovered row is still fileIsMissing', async () => {
    seedProcessingItem({ applicationId: null, applicationStatus: null, phase: 'creating' });

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });
    await waitFor(() => {
      expect(fileIsMissing(result.current.items[0])).toBe(true);
    });
    // Give the bootstrap effect's own auto-triggered start() time to run its
    // full (near-instant, since nothing is processable) cycle rather than
    // asserting mid-flight.
    await waitFor(() => {
      expect(result.current.running).toBe(false);
    });

    // Nothing to run -- the only row still needs a real file re-attached by
    // hand (no IndexedDB record ever existed for a queue this old), so
    // start() -- called automatically on mount, not by this test -- must
    // finish immediately without calling createApplication.
    expect(createApplication).not.toHaveBeenCalled();
    expect(result.current.items[0].status).toBe('pending');
  });

  it("start()'s return value reports how many rows are still blocked on a missing file, for a manual Resume click", async () => {
    seedProcessingItem({ applicationId: null, applicationStatus: null, phase: 'creating' });

    const { result } = renderHook(() => useBatchUploadStore(), { wrapper });
    await waitFor(() => {
      expect(result.current.running).toBe(false);
    });

    let startResult;
    await act(async () => {
      startResult = await result.current.start();
    });

    expect(startResult).toEqual({ remainingMissingFileCount: 1 });
  });
});
