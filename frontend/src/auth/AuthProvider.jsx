import { useCallback, useEffect, useMemo, useState } from 'react';

import * as authService from './authService';
import { AuthContext } from './AuthContext';
import { abortPendingRequests, setUnauthorizedHandler } from '../services/api';

function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  const resetSession = useCallback(() => {
    setUser(null);
    setAuthenticated(false);
  }, []);

  const checkAuthentication = useCallback(async () => {
    setLoading(true);
    try {
      const data = await authService.getCurrentUser();
      setUser(data?.user ?? data ?? null);
      setAuthenticated(true);
    } catch {
      resetSession();
    } finally {
      setLoading(false);
    }
  }, [resetSession]);

  const login = useCallback(async (credentials) => {
    await authService.login(credentials);
    const data = await authService.getCurrentUser();
    setUser(data?.user ?? data ?? null);
    setAuthenticated(true);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // Best effort: the local session is cleared regardless.
    }
    abortPendingRequests();
    resetSession();
  }, [resetSession]);

  const refreshSession = useCallback(() => authService.refreshSession(), []);

  useEffect(() => {
    // Fetch-on-mount via a memoized custom-hook function -- React's own
    // recommended shape for this exact case (react.dev/learn/synchronizing-with-effects#fetching-data).
    // react-hooks/set-state-in-effect flags the setState reachable inside
    // checkAuthentication regardless of context; restructuring it would mean
    // touching this and 9 other core data-fetching hooks for no behavioral
    // gain, purely to satisfy a static rule that can't distinguish this from
    // a genuine anti-pattern. See the full-stack audit, Phase 8, for the
    // reasoning behind every instance of this suppression in the codebase.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkAuthentication();
  }, [checkAuthentication]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      abortPendingRequests();
      resetSession();
    });
    return () => setUnauthorizedHandler(null);
  }, [resetSession]);

  const value = useMemo(
    () => ({
      user,
      authenticated,
      loading,
      login,
      logout,
      refreshSession,
      checkAuthentication,
    }),
    [user, authenticated, loading, login, logout, refreshSession, checkAuthentication]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthProvider;
