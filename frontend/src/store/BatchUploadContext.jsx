import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { uploadBulkDocument } from '../services/documents';
import { getProcessingProgress, startProcessing } from '../services/processing';
import { mapApplicationStatusToBatchStatus } from '../data/batchStatuses';
import { getApiErrorMessage } from '../utils/apiError';
import { useApplicationsStore } from './ApplicationsContext';
import * as batchFileStore from './batchFileStore';

//: How often to re-check an in-flight application's status while waiting
//: for it to reach a terminal state. Matches the cadence already used by
//: useProcessingProgress.js / useProcessingOverview.js elsewhere in the app.
const POLL_INTERVAL_MS = 2500;

//: A single stuck/misbehaving file must never hang the whole batch
//: (requirement: continue past a failure instead of stopping). Generous
//: enough to cover the queue's own retry backoff (bulk_queue_max_attempts=3
//: with exponential backoff off bulk_queue_retry_backoff_seconds) plus real
//: OCR/analysis time, while still guaranteeing forward progress.
const PER_FILE_TIMEOUT_MS = 10 * 60 * 1000;

//: Real incident, 2026-09-14: a 34-file batch lost all record of its 32
//: still-pending files the moment the browser/dev-server session ended --
//: this context previously held the queue only in React state, with
//: nothing written anywhere else. Persisting a snapshot here means a page
//: reload (or the dev server restarting) doesn't erase the record of what
//: was queued -- item metadata (filename, status, progress, application id)
//: lives here. A browser File's actual bytes cannot be part of this
//: JSON-serialized snapshot at all (not a design choice -- the File/Blob
//: APIs simply don't allow it); those live separately in `batchFileStore`
//: (IndexedDB, which *can* hold real file bytes across a reload) and get
//: re-attached to a restored item automatically on mount -- see the
//: bootstrap effect inside BatchUploadProvider for both that recovery and
//: the reconciliation of a restored item's real status against the server.
//: fileIsMissing() below is the honest fallback for when that recovery
//: doesn't find anything (storage quota exceeded when the file was first
//: added, site data cleared, private browsing, or a queue started before
//: this recovery layer existed) -- not the default outcome of a reload.
const STORAGE_KEY = 'onboarding-system.batchUploadQueue.v1';

const BatchUploadContext = createContext(null);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isPdfFile(file) {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
}

//: `file` (a browser File object) is deliberately excluded -- see STORAGE_KEY
//: above for why it can never be persisted, restored, or JSON-serialized at
//: all (JSON.stringify silently turns a File into `{}`, which would be
//: actively misleading to round-trip through storage as if it were real).
function serializableItem(item) {
  const copy = { ...item };
  delete copy.file;
  return copy;
}

function loadPersistedItems() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // Corrupted or inaccessible storage (private browsing, quota, etc.) --
    // start with an empty queue rather than throwing during render.
    return [];
  }
}

function nextIdCounterFrom(items) {
  let max = 0;
  for (const item of items) {
    const match = /^batch-(\d+)$/.exec(item.clientId ?? '');
    if (match) {
      max = Math.max(max, Number(match[1]));
    }
  }
  return max;
}

//: Whether an item still needs its file re-attached by hand -- normally
//: true only briefly, right after a restore and before the bootstrap
//: effect's IndexedDB recovery finishes (see STORAGE_KEY above), or
//: permanently true if that recovery genuinely found nothing to restore.
export function fileIsMissing(item) {
  return !item.file && item.status === 'pending';
}

/**
 * Client-side preview of the application name the backend will derive from
 * this filename (mirrors `Path(filename).stem`: strip only the last
 * extension, keep everything else -- spaces, case, the rest of the name --
 * untouched). The real name is authoritative once the application is
 * created and refreshed from the server; this is only shown before that.
 */
function derivePreviewName(filename) {
  const dotIndex = filename.lastIndexOf('.');
  if (dotIndex <= 0) {
    return filename;
  }
  return filename.slice(0, dotIndex);
}

/**
 * Provider for the multi-PDF batch upload queue.
 *
 * Mounted at the app root (see ProtectedLayout.jsx), nested inside
 * ApplicationsProvider (it consumes `create`/`refreshApplication` from that
 * store) so the queue keeps running -- and the Applications list stays in
 * sync -- even if the user navigates away from the batch-upload page and
 * back.
 *
 * Each queued file is processed strictly one at a time: create its
 * application, upload the PDF, start processing, then poll until that one
 * application reaches a terminal state before the next pending file is
 * even submitted. A failure at any step marks that file Failed and moves on
 * to the next one -- it never stops the queue.
 */
export function BatchUploadProvider({ children }) {
  const applicationsStore = useApplicationsStore();
  const [items, setItems] = useState(loadPersistedItems);
  const [running, setRunning] = useState(false);
  const itemsRef = useRef(items);
  const runningRef = useRef(false);
  const cancelledRef = useRef(false);
  const idCounterRef = useRef(nextIdCounterFrom(items));
  const bootstrappedRef = useRef(false);

  const applyItems = useCallback((updater) => {
    itemsRef.current = typeof updater === 'function' ? updater(itemsRef.current) : updater;
    setItems(itemsRef.current);
  }, []);

  // Persist on every change. Deliberately unconditional (not just on
  // add/remove) -- progress percentages and phase labels are exactly what a
  // reload should be able to show accurately, per STORAGE_KEY's own reasoning
  // above, so status updates mid-file need saving too, not just the big
  // queue-membership changes.
  useEffect(() => {
    try {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(items.map(serializableItem))
      );
    } catch {
      // Storage full/unavailable (private browsing, quota) -- the queue
      // still works for this session, it just won't survive a reload.
    }
  }, [items]);

  const updateItem = useCallback(
    (clientId, patch) => {
      applyItems((prev) =>
        prev.map((item) => (item.clientId === clientId ? { ...item, ...patch } : item))
      );
    },
    [applyItems]
  );

  const addFiles = useCallback(
    (fileList) => {
      const files = Array.from(fileList ?? []);
      const pdfFiles = files.filter(isPdfFile);
      const skippedCount = files.length - pdfFiles.length;
      if (pdfFiles.length > 0) {
        const newItems = pdfFiles.map((file) => ({
          clientId: `batch-${++idCounterRef.current}`,
          file,
          filename: file.name,
          previewName: derivePreviewName(file.name),
          status: 'pending',
          phase: null,
          progress: 0,
          applicationId: null,
          applicationName: null,
          applicationStatus: null,
          error: null,
        }));
        applyItems((prev) => [...prev, ...newItems]);
        // Fire-and-forget: stores each file's actual bytes in IndexedDB so
        // it can survive a real page reload (see STORAGE_KEY's own
        // writeup). A failure here (quota exceeded, private browsing) just
        // means this one file falls back to the pre-existing
        // needs-re-adding-by-hand behavior -- never blocks adding it to the
        // in-memory queue, which always works regardless of storage.
        for (const item of newItems) {
          batchFileStore.putFile(item.clientId, item.file).catch(() => {});
        }
      }
      return { addedCount: pdfFiles.length, skippedCount };
    },
    [applyItems]
  );

  const removeFile = useCallback(
    (clientId) => {
      applyItems((prev) =>
        prev.filter((item) => !(item.clientId === clientId && item.status === 'pending'))
      );
      batchFileStore.deleteFile(clientId).catch(() => {});
    },
    [applyItems]
  );

  const reset = useCallback(() => {
    if (runningRef.current) {
      return;
    }
    applyItems([]);
    batchFileStore.clearAllFiles().catch(() => {});
  }, [applyItems]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
  }, []);

  const pollUntilTerminal = useCallback(
    async (applicationId, clientId) => {
      const deadline = Date.now() + PER_FILE_TIMEOUT_MS;
      while (true) {
        // Real OCR/analysis progress (documents completed out of the
        // application's own total), not a guess -- reuses the exact same
        // endpoint the Processing page's useProcessingOverview already polls,
        // so the batch queue table's progress bar during this phase reflects
        // the same numbers a user would see there.
        const [result, progress] = await Promise.all([
          applicationsStore.refreshApplication(applicationId),
          getProcessingProgress(applicationId).catch(() => null),
        ]);
        if (progress) {
          const total = Number(progress.total_documents) || 0;
          const completed = Number(progress.completed) || 0;
          updateItem(clientId, { progress: total ? Math.round((completed / total) * 100) : 0 });
        }
        if (result.ok) {
          updateItem(clientId, {
            applicationStatus: result.application.status,
            applicationName: result.application.name,
          });
          const batchStatus = mapApplicationStatusToBatchStatus(result.application.status);
          if (batchStatus !== 'processing') {
            return batchStatus;
          }
        }
        // A transient fetch error keeps polling rather than failing the file
        // immediately -- only the overall per-file timeout below gives up.
        if (Date.now() > deadline) {
          updateItem(clientId, { error: 'Processing timed out.' });
          return 'failed';
        }
        await sleep(POLL_INTERVAL_MS);
      }
    },
    [applicationsStore, updateItem]
  );

  const processItem = useCallback(
    async (clientId) => {
      const item = itemsRef.current.find((candidate) => candidate.clientId === clientId);
      if (!item) {
        return;
      }

      updateItem(clientId, { status: 'processing', phase: 'creating', error: null });
      const createResult = await applicationsStore.create({ notes: null });
      if (!createResult.ok) {
        updateItem(clientId, { status: 'failed', phase: null, error: createResult.error });
        return;
      }

      const applicationId = createResult.application.id;
      updateItem(clientId, {
        applicationId,
        applicationStatus: createResult.application.status,
        phase: 'uploading',
        progress: 0,
      });

      try {
        await uploadBulkDocument({
          applicationId,
          file: item.file,
          onUploadProgress: (event) => {
            if (!event.total) {
              return;
            }
            updateItem(clientId, { progress: Math.round((event.loaded / event.total) * 100) });
          },
        });
      } catch (err) {
        updateItem(clientId, { status: 'failed', phase: null, error: getApiErrorMessage(err) });
        return;
      }

      // Picks up the server-derived application name (filename minus only
      // the .pdf extension) so the queue table shows the real name, not
      // just the client-side preview.
      const refreshed = await applicationsStore.refreshApplication(applicationId);
      if (refreshed.ok) {
        updateItem(clientId, {
          applicationName: refreshed.application.name,
          applicationStatus: refreshed.application.status,
        });
      }

      updateItem(clientId, { phase: 'starting' });
      try {
        // Called unconditionally, unlike the single-file upload page's own
        // "autoStartProcessingAfterUpload" preference gate: this feature's
        // entire premise is unattended automatic processing, so silently
        // respecting a preference that could be off elsewhere would break
        // it for anyone who'd disabled that setting.
        await startProcessing(applicationId);
      } catch (err) {
        updateItem(clientId, { status: 'failed', phase: null, error: getApiErrorMessage(err) });
        return;
      }

      updateItem(clientId, { phase: 'polling' });
      const finalStatus = await pollUntilTerminal(applicationId, clientId);
      updateItem(clientId, { status: finalStatus, phase: null });
    },
    [applicationsStore, pollUntilTerminal, updateItem]
  );

  const start = useCallback(async () => {
    if (runningRef.current) {
      return { remainingMissingFileCount: 0 };
    }
    runningRef.current = true;
    cancelledRef.current = false;
    setRunning(true);
    try {
      while (true) {
        if (cancelledRef.current) {
          break;
        }
        // fileIsMissing() items are also 'pending' but have no File object
        // to upload (restored from storage after a reload -- see
        // STORAGE_KEY's own reasoning) -- skipped here rather than crashing
        // partway through processItem on a null file. They stay in the
        // queue so the user sees they need re-adding, via removeFile() +
        // addFiles() with the real file, rather than silently vanishing.
        const next = itemsRef.current.find(
          (item) => item.status === 'pending' && !fileIsMissing(item)
        );
        if (!next) {
          break;
        }
        // Cancel stops the loop from *starting* the next file; it never
        // aborts the file already in flight, so that file's status stays
        // honest (it runs to its own real terminal state).
        await processItem(next.clientId);
      }
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
    // Told to the caller (not just left to the table's own per-row text)
    // so a click that visibly does nothing -- every remaining pending item
    // needs its file re-added -- can be explained immediately, e.g. via a
    // toast, rather than looking like the batch silently refused to resume.
    const remainingMissingFileCount = itemsRef.current.filter(
      (item) => item.status === 'pending' && fileIsMissing(item)
    ).length;
    return { remainingMissingFileCount };
  }, [processItem]);

  // Runs once on mount: recovers each restored, still-pending item's actual
  // file bytes from IndexedDB (see STORAGE_KEY/batchFileStore), and
  // reconciles a restored 'processing' item's status against the real
  // server rather than trusting whatever it was the instant the previous
  // session ended -- either it finished/failed for real while nobody was
  // watching, or it got deleted entirely (see STORAGE_KEY's own incident
  // writeup), both of which make the stored status wrong. Items with no
  // applicationId yet (the create() call itself never finished) have
  // nothing on the server to check, so they just become pending again --
  // file recovery is what determines whether they also stay fileIsMissing().
  //
  // Once both finish, if the page loaded with genuinely unfinished work
  // (something still pending or processing), resume automatically rather
  // than leaving now-recovered, ready-to-run files sitting idle until the
  // user notices and clicks Resume by hand -- a real page reload should not
  // be something the user has to actively recover from.
  useEffect(() => {
    if (bootstrappedRef.current) {
      return;
    }
    bootstrappedRef.current = true;

    const hadIncompleteWork = itemsRef.current.some(
      (item) => item.status === 'pending' || item.status === 'processing'
    );

    const recoverFiles = async () => {
      const toRecover = itemsRef.current.filter(
        (item) => item.status === 'pending' && fileIsMissing(item)
      );
      await Promise.all(
        toRecover.map(async (item) => {
          try {
            const file = await batchFileStore.getFile(item.clientId);
            if (file) {
              updateItem(item.clientId, { file });
            }
          } catch {
            // IndexedDB unavailable or nothing stored for this item -- it
            // stays fileIsMissing() and needs re-adding by hand, the same
            // graceful fallback as before this recovery layer existed.
          }
        })
      );
    };

    const reconcileProcessing = async () => {
      const toReconcile = itemsRef.current.filter((item) => item.status === 'processing');
      await Promise.all(
        toReconcile.map(async (item) => {
          if (!item.applicationId) {
            updateItem(item.clientId, { status: 'pending', phase: null, error: null });
            return;
          }
          const result = await applicationsStore.refreshApplication(item.applicationId);
          if (!result.ok) {
            updateItem(item.clientId, {
              status: 'failed',
              phase: null,
              error: `${result.error} (this may be because the application was deleted while the batch was running)`,
            });
            return;
          }
          const batchStatus = mapApplicationStatusToBatchStatus(result.application.status);
          updateItem(item.clientId, {
            applicationStatus: result.application.status,
            applicationName: result.application.name,
          });
          if (batchStatus !== 'processing') {
            updateItem(item.clientId, { status: batchStatus, phase: null });
            return;
          }
          // Genuinely still processing server-side -- resume waiting for it
          // exactly as if this session had started it, instead of leaving
          // it stuck showing "Processing..." with nothing watching it.
          updateItem(item.clientId, { phase: 'polling' });
          const finalStatus = await pollUntilTerminal(item.applicationId, item.clientId);
          updateItem(item.clientId, { status: finalStatus, phase: null });
        })
      );
    };

    Promise.all([recoverFiles(), reconcileProcessing()]).then(() => {
      if (hadIncompleteWork && !runningRef.current) {
        start();
      }
    });
  }, [applicationsStore, pollUntilTerminal, start, updateItem]);

  const counts = useMemo(() => {
    const totals = {
      total: items.length,
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
      needsFile: 0,
    };
    for (const item of items) {
      totals[item.status] += 1;
      if (fileIsMissing(item)) {
        totals.needsFile += 1;
      }
    }
    return totals;
  }, [items]);

  const value = useMemo(
    () => ({ items, counts, running, addFiles, removeFile, start, cancel, reset }),
    [items, counts, running, addFiles, removeFile, start, cancel, reset]
  );

  return <BatchUploadContext.Provider value={value}>{children}</BatchUploadContext.Provider>;
}

export function useBatchUploadStore() {
  const context = useContext(BatchUploadContext);
  if (!context) {
    throw new Error('useBatchUploadStore must be used within a BatchUploadProvider');
  }
  return context;
}
