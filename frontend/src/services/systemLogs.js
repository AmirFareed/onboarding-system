import api from './api';

/**
 * Search the system log (IT view).
 *
 * Thin wrapper over `GET /system-logs`: server-side filtered, paginated,
 * newest-first access to the shared audit log. Every filter is optional and
 * only sent when set.
 *
 * @param {object} [filters]
 * @param {string} [filters.actor] Substring match on the acting username.
 * @param {string} [filters.eventType] Exact match on the action identifier.
 * @param {string} [filters.severity] Exact match on severity (e.g. "INFO").
 * @param {string} [filters.dateFrom] ISO datetime, inclusive lower bound.
 * @param {string} [filters.dateTo] ISO datetime, exclusive upper bound.
 * @param {string} [filters.query] Free-text substring match on username/action.
 * @param {boolean} [filters.includeOrphaned] Include entries whose
 *   application was later deleted (excluded by default -- see the backend
 *   route's own description).
 * @param {object} [options]
 * @param {number} [options.offset] Number of log entries to skip.
 * @param {number} [options.limit] Maximum number of log entries to return.
 * @returns {Promise<{items: object[], total: number, offset: number, limit: number}>}
 */
export function listSystemLogs(
  { actor, eventType, severity, dateFrom, dateTo, query, includeOrphaned } = {},
  { offset = 0, limit = 50 } = {}
) {
  return api
    .get('/system-logs', {
      params: {
        offset,
        limit,
        ...(actor ? { actor } : {}),
        ...(eventType ? { event_type: eventType } : {}),
        ...(severity ? { severity } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
        ...(query ? { query } : {}),
        ...(includeOrphaned ? { include_orphaned: true } : {}),
      },
    })
    .then((response) => response.data);
}

/**
 * Fetch a single system log entry by id.
 *
 * @param {number|string} logId Log entry id.
 * @returns {Promise<object>} The full stored log record.
 */
export function getSystemLog(logId) {
  return api.get(`/system-logs/${logId}`).then((response) => response.data);
}
