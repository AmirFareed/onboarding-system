/**
 * Reusable comparison helpers for client-side sorting.
 *
 * `sortBy` is a pure, side-effect-free sorter over an array of objects. It is
 * used by the applications hook and kept generic so future modules can reuse it.
 */

/**
 * Compare two values of mixed types.
 *
 * Dates may arrive as ISO strings or Date instances; ids are numbers; text is
 * compared case-insensitively with numeric-aware ordering. Null/undefined
 * values sort first.
 *
 * @param {unknown} a
 * @param {unknown} b
 * @returns {number} Negative, zero or positive.
 */
export function compareValues(a, b) {
  if (a === b) {
    return 0;
  }
  if (a == null) {
    return -1;
  }
  if (b == null) {
    return 1;
  }

  if (a instanceof Date || b instanceof Date || isIsoDate(a) || isIsoDate(b)) {
    const ta = new Date(a).getTime();
    const tb = new Date(b).getTime();
    return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb);
  }

  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }

  return String(a).localeCompare(String(b), undefined, {
    numeric: true,
    sensitivity: 'base',
  });
}

/**
 * Return a new array sorted by `key`, leaving the input untouched.
 *
 * @param {Array<object>} items Array to sort.
 * @param {string} key Field to order by.
 * @param {'asc'|'desc'} [direction] Sort direction.
 * @returns {Array<object>} A new, sorted array.
 */
export function sortBy(items, key, direction = 'asc') {
  const factor = direction === 'desc' ? -1 : 1;
  return [...items].sort((a, b) => factor * compareValues(a[key], b[key]));
}

function isIsoDate(value) {
  return (
    typeof value === 'string' &&
    /^\d{4}-\d{2}-\d{2}/.test(value) &&
    !Number.isNaN(Date.parse(value))
  );
}
