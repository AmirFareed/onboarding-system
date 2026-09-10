import { createContext, useCallback, useEffect, useMemo, useState } from 'react';

import { applyTheme, getStoredPreference } from './theme';

export const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(getStoredPreference);

  useEffect(() => {
    try {
      window.localStorage.setItem('fintech-theme-preference', preference);
    } catch {
      // Ignore storage failures (private mode, disabled storage).
    }
    applyTheme(preference);
  }, [preference]);

  const setTheme = useCallback((next) => {
    setPreference(next);
  }, []);

  const value = useMemo(
    () => ({
      theme: preference,
      resolvedTheme: preference,
      setTheme,
    }),
    [preference, setTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
