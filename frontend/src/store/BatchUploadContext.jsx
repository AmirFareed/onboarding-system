import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

import { uploadBulkDocument } from '../services/documents';
import { getProcessingProgress, startProcessing } from '../services/processing';
import { mapApplicationStatusToBatchStatus } from '../data/batchStatuses';
import { getApiErrorMessage } from '../utils/apiError';
import { useApplicationsStore } from './ApplicationsContext';

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

const BatchUploadContext = createContext(null);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isPdfFile(file) {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
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
  const [items, setItems] = useState([]);
  const [running, setRunning] = useState(false);
  const itemsRef = useRef([]);
  const runningRef = useRef(false);
  const cancelledRef = useRef(false);
  const idCounterRef = useRef(0);

  const applyItems = useCallback((updater) => {
    itemsRef.current = typeof updater === 'function' ? updater(itemsRef.current) : updater;
    setItems(itemsRef.current);
  }, []);

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
    },
    [applyItems]
  );

  const reset = useCallback(() => {
    if (runningRef.current) {
      return;
    }
    applyItems([]);
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
      return;
    }
    runningRef.current = true;
    cancelledRef.current = false;
    setRunning(true);
    try {
      while (true) {
        if (cancelledRef.current) {
          break;
        }
        const next = itemsRef.current.find((item) => item.status === 'pending');
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
  }, [processItem]);

  const counts = useMemo(() => {
    const totals = { total: items.length, pending: 0, processing: 0, completed: 0, failed: 0 };
    for (const item of items) {
      totals[item.status] += 1;
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
