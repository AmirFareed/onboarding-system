const STORAGE_KEY = 'fintech-workspace-preferences';

/**
 * Workspace preference defaults.
 *
 * These are the out-of-the-box behaviours. Preferences are stored locally on
 * the device under a single key and picked up by consumers at read time, so
 * no global state system is required — navigating after a change is enough for
 * the next mount to observe the new value.
 */
export const PREFERENCE_DEFAULTS = {
  rememberApplicationFilter: true,
  rememberLastOpenedApplication: true,
  confirmBeforeRejectApplication: true,
  autoStartProcessingAfterUpload: true,
  autoRefreshProcessingStatus: true,
  openReportOnProcessingComplete: false,
};

/**
 * Read the stored preference object merged over the defaults.
 *
 * @returns {object} Every preference key with a concrete value.
 */
export function getPreferences() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return { ...PREFERENCE_DEFAULTS };
    }
    const parsed = JSON.parse(stored);
    return { ...PREFERENCE_DEFAULTS, ...parsed };
  } catch {
    return { ...PREFERENCE_DEFAULTS };
  }
}

/**
 * Read a single preference value, falling back to its default.
 *
 * @param {string} key Preference key.
 * @param {*} [fallback] Optional fallback when the key is unknown.
 * @returns {*} The stored value, or the default for the key.
 */
export function getPreference(key, fallback) {
  const all = getPreferences();
  return Object.prototype.hasOwnProperty.call(all, key) ? all[key] : fallback;
}

/**
 * Persist a single preference value.
 *
 * @param {string} key Preference key.
 * @param {*} value The value to store.
 */
export function setPreference(key, value) {
  const next = { ...getPreferences(), [key]: value };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage failures (private mode, disabled storage).
  }
  return next;
}
