import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import {
  createApplication,
  deleteApplication,
  getApplication,
  listApplications,
} from '../services/applications';
import { listDocuments } from '../services/documents';
import { getApiErrorMessage } from '../utils/apiError';
import { sortBy } from '../utils/sort';

const RECENT_LIMIT = 5;

const ApplicationsContext = createContext(null);

/**
 * Single shared source of truth for the application list and the documents
 * belonging to each application.
 *
 * Both the Applications page and the Dashboard "Recent Applications" section
 * read from this store, so a newly created application appears in both places
 * through the one update performed by `create`. Document state is tracked per
 * application here too: the dashboard's per-application upload checklist and
 * the upload page read and mutate the same map, so progress stays consistent
 * across both views. The provider mounts inside the protected layout, so the
 * data only loads for authenticated sessions.
 */
export function ApplicationsProvider({ children }) {
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [documentsByApplication, setDocumentsByApplication] = useState({});
  const fetchedRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { items } = await listApplications({ limit: 100 });
      setApplications(items);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (fetchedRef.current) {
      return;
    }
    fetchedRef.current = true;
    load();
  }, [load]);

  const reload = useCallback(() => {
    fetchedRef.current = true;
    return load();
  }, [load]);

  const refreshApplication = useCallback(async (applicationId) => {
    try {
      const application = await getApplication(applicationId);
      setApplications((items) =>
        items.map((item) => (item.id === application.id ? application : item))
      );
      return { ok: true, application };
    } catch (err) {
      return { ok: false, error: getApiErrorMessage(err) };
    }
  }, []);

  const create = useCallback(async ({ notes }) => {
    try {
      const application = await createApplication({ notes });
      setApplications((items) => [application, ...items]);
      return { ok: true, application };
    } catch (err) {
      return { ok: false, error: getApiErrorMessage(err) };
    }
  }, []);

  const remove = useCallback(async (applicationId) => {
    try {
      await deleteApplication(applicationId);
      setApplications((items) => items.filter((item) => item.id !== applicationId));
      setDocumentsByApplication((state) => {
        if (!(applicationId in state)) {
          return state;
        }
        const next = { ...state };
        delete next[applicationId];
        return next;
      });
      return { ok: true };
    } catch (err) {
      return { ok: false, error: getApiErrorMessage(err) };
    }
  }, []);

  const loadDocuments = useCallback(async (applicationId) => {
    setDocumentsByApplication((state) => ({
      ...state,
      [applicationId]: { ...(state[applicationId] ?? {}), loading: true, error: null },
    }));
    try {
      const { items } = await listDocuments(applicationId);
      setDocumentsByApplication((state) => ({
        ...state,
        [applicationId]: { items, loading: false, error: null },
      }));
      return { ok: true, items };
    } catch (err) {
      const message = getApiErrorMessage(err);
      setDocumentsByApplication((state) => ({
        ...state,
        [applicationId]: { ...(state[applicationId] ?? {}), loading: false, error: message },
      }));
      return { ok: false, error: message };
    }
  }, []);

  const setDocumentItems = useCallback((applicationId, items) => {
    setDocumentsByApplication((state) => ({
      ...state,
      [applicationId]: { items, loading: false, error: null },
    }));
  }, []);

  const recentApplications = useMemo(
    () => sortBy(applications, 'updated_at', 'desc').slice(0, RECENT_LIMIT),
    [applications]
  );

  const value = useMemo(
    () => ({
      applications,
      recentApplications,
      total: applications.length,
      loading,
      error,
      reload,
      refreshApplication,
      create,
      remove,
      documentsByApplication,
      loadDocuments,
      setDocumentItems,
    }),
    [
      applications,
      recentApplications,
      loading,
      error,
      reload,
      refreshApplication,
      create,
      remove,
      documentsByApplication,
      loadDocuments,
      setDocumentItems,
    ]
  );

  return <ApplicationsContext.Provider value={value}>{children}</ApplicationsContext.Provider>;
}

export function useApplicationsStore() {
  const context = useContext(ApplicationsContext);
  if (!context) {
    throw new Error('useApplicationsStore must be used within an ApplicationsProvider');
  }
  return context;
}
