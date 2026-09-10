/**
 * Format an ISO datetime string as a readable date, e.g. "Aug 7, 2026".
 *
 * @param {string | null | undefined} iso The value to format.
 * @returns {string} A formatted date, or an en-dash when empty.
 */
export function formatDate(iso) {
  if (!iso) {
    return '\u2014';
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '\u2014'
    : date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
}

/**
 * Format an ISO datetime string with a time component, e.g. "Aug 7, 2026, 2:30 PM".
 *
 * @param {string | null | undefined} iso The value to format.
 * @returns {string} A formatted datetime, or an en-dash when empty.
 */
export function formatDateTime(iso) {
  if (!iso) {
    return '\u2014';
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '\u2014'
    : date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
}

/**
 * Format a duration in seconds as a compact human-readable span.
 *
 * e.g. 45 -> "45s", 3725 -> "1h 2m", 223200 -> "2d 14h". Values below a
 * minute show seconds so short spans stay visible; anything larger drops the
 * least significant unit to keep the label short.
 *
 * @param {number|null|undefined} seconds Duration to format.
 * @returns {string} A readable duration, or an en-dash when empty.
 */
export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) {
    return '\u2014';
  }
  const total = Math.max(0, Math.round(Number(seconds)));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (days > 0) {
    return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  }
  if (hours > 0) {
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  if (minutes > 0) {
    return `${minutes}m`;
  }
  return `${secs}s`;
}

/**
 * Turn a SCREAMING_SNAKE_CASE backend enum value into a readable label,
 * e.g. "document_completeness" -> "Document Completeness".
 *
 * @param {string | null | undefined} value The raw enum value.
 * @returns {string} A title-cased label, or an en-dash when empty.
 */
export function humanizeEnum(value) {
  if (!value) {
    return '\u2014';
  }
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
