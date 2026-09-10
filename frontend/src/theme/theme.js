export const THEME_OPTIONS = ['light', 'dark', 'black', 'mint', 'cherry'];

export const THEME_PREFERENCE_KEY = 'fintech-theme-preference';

export const DEFAULT_THEME = 'light';

export function getStoredPreference() {
  try {
    const stored = window.localStorage.getItem(THEME_PREFERENCE_KEY);
    if (stored && THEME_OPTIONS.includes(stored)) {
      return stored;
    }
    // Theme options used to include 'system'. That mode no longer exists, but
    // a user who chose it before this redesign shouldn't be silently reset to
    // light -- resolve it once against the OS preference instead.
    if (stored === 'system' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
  } catch {
    return DEFAULT_THEME;
  }
  return DEFAULT_THEME;
}

export function applyTheme(resolvedTheme) {
  document.documentElement.setAttribute('data-theme', resolvedTheme);
}
