import axios from 'axios';

/**
 * Shared axios instance for the backend API.
 *
 * The instance uses cookie-based authentication (withCredentials) and a
 * relative base URL so the same build works in development (the Vite dev
 * server proxies /api/v1 to the FastAPI backend) and behind a reverse proxy in
 * production. Deployments that host the backend on a separate origin should
 * set VITE_API_BASE_URL in a .env.local file to the absolute backend URL (see
 * .env.example).
 *
 * A response interceptor transparently handles an expired access token: it
 * attempts a single POST /auth/refresh, queues concurrent 401s and retries the
 * original request once. If refresh fails, the registered unauthorized handler
 * (the auth provider) is notified so the session can be cleared.
 */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

let isRefreshing = false;
let failedQueue = [];
let unauthorizedHandler = null;

function isAuthEndpoint(url) {
  return /\/auth\/(login|refresh)$/.test(url ?? '');
}

function processQueue(error) {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else {
      promise.resolve();
    }
  });
  failedQueue = [];
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function notifyUnauthorized() {
  if (unauthorizedHandler) {
    unauthorizedHandler();
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (axios.isCancel(error)) {
      return Promise.reject(error);
    }
    if (
      !original ||
      original._retried ||
      original._skipAuthRefresh ||
      isAuthEndpoint(original.url) ||
      error.response?.status !== 401
    ) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then(() => api(original))
        .catch((retryError) => Promise.reject(retryError));
    }

    original._retried = true;
    isRefreshing = true;

    try {
      await api.post('/auth/refresh', {}, { _skipAuthRefresh: true });
      processQueue(null);
      return await api(original);
    } catch (refreshError) {
      processQueue(refreshError);
      notifyUnauthorized();
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

const pendingControllers = new Set();

api.interceptors.request.use((config) => {
  if (config.signal) {
    return config;
  }
  const controller = new AbortController();
  config.signal = controller.signal;
  pendingControllers.add(controller);
  config.signal.addEventListener(
    'abort',
    () => pendingControllers.delete(controller),
    { once: true }
  );
  return config;
});

export function abortPendingRequests() {
  pendingControllers.forEach((controller) => controller.abort());
  pendingControllers.clear();
}

export default api;
