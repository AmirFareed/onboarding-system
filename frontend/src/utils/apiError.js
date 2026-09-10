/**
 * Extract a human-readable message from an axios error.
 *
 * The backend returns `{detail: string}` for single errors and
 * `{detail: [...]}` (array of per-field objects) for 422 validation failures.
 * Network and timeout failures produce their own generic messages.
 *
 * @param {object} error An axios error object.
 * @returns {string} A message suitable for display in a toast or banner.
 */
export function getApiErrorMessage(error) {
  if (!error?.response) {
    if (error?.code === 'ECONNABORTED') {
      return 'The request timed out. Please try again.';
    }
    return 'Could not reach the server. Check your connection and try again.';
  }

  const { status, data } = error.response;
  const detail = data?.detail;

  if (Array.isArray(detail)) {
    const first = detail.find((item) => item?.msg);
    return first?.msg ?? 'The request could not be validated.';
  }

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  const fallbacks = {
    400: 'The request was invalid.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested resource was not found.',
    409: 'A duplicate upload was rejected.',
    413: 'The file exceeds the maximum allowed size.',
    422: 'The request could not be validated.',
    500: 'Something went wrong on the server.',
  };
  return fallbacks[status] ?? 'An unexpected error occurred.';
}
