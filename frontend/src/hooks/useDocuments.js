import { useCallback, useEffect, useMemo, useState } from 'react';

import { uploadBulkDocument } from '../services/documents';
import { getApiErrorMessage } from '../utils/apiError';
import { useApplicationsStore } from '../store/ApplicationsContext';

/**
 * Load and manage the documents of a single application.
 *
 * A thin consumer of the shared applications store, so the dashboard checklist
 * and the upload page always see the same document state. `pending` maps an
 * operation key to its in-flight state so the bulk upload zone can render an
 * "Uploading" state with a live progress bar. `uploadBulk` never throws; it
 * returns `{ ok, error?, data? }` so the page owns toasts.
 *
 * @param {number|string} applicationId Application id.
 */
export function useDocuments(applicationId) {
  const { documentsByApplication, loadDocuments, refreshApplication } = useApplicationsStore();
  const [pending, setPending] = useState({});

  const state = documentsByApplication[applicationId] ?? {};
  const { items: documents = [], loading = true, error = null } = state;

  const reload = useCallback(() => loadDocuments(applicationId), [applicationId, loadDocuments]);

  useEffect(() => {
    reload();
  }, [reload]);

  const setPendingProgress = (documentId, progress) => {
    setPending((prev) => ({ ...prev, [documentId]: { ...prev[documentId], progress } }));
  };

  const clearPending = (documentId) => {
    setPending((prev) => {
      const next = { ...prev };
      delete next[documentId];
      return next;
    });
  };

  const uploadBulk = useCallback(
    async (file) => {
      const operationKey = 'upload-bulk';
      setPending((prev) => ({
        ...prev,
        [operationKey]: { phase: 'upload', progress: 0 },
      }));

      const onUploadProgress = (event) => {
        if (event.total) {
          setPendingProgress(operationKey, Math.round((event.loaded / event.total) * 100));
        }
      };

      try {
        const response = await uploadBulkDocument({
          applicationId,
          file,
          onUploadProgress,
        });

        clearPending(operationKey);
        // We reload all documents so the newly extracted copies appear in the list.
        await reload();
        // The bulk upload may give the application its display name; refresh the
        // store's copy so the Applications list and dashboard reflect it.
        refreshApplication(applicationId);
        return { ok: true, data: response };
      } catch (err) {
        clearPending(operationKey);
        return { ok: false, error: getApiErrorMessage(err) };
      }
    },
    [applicationId, reload, refreshApplication]
  );

  return useMemo(
    () => ({
      documents,
      loading,
      error,
      reload,
      pending,
      uploadBulk,
    }),
    [documents, loading, error, reload, pending, uploadBulk]
  );
}
