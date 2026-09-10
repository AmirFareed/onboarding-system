import { useCallback, useEffect, useRef, useState } from 'react';
import { Clock } from 'lucide-react';

import { useAuth } from '../../../hooks/useAuth';
import Spinner from '../../common/Spinner/Spinner';
import styles from './SessionTimeoutModal.module.css';

const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const WARNING_MS = 5 * 60 * 1000;
const CHECK_INTERVAL_MS = 15 * 1000;
const ACTIVITY_EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];

function SessionTimeoutModal() {
  const { refreshSession, logout } = useAuth();
  // Date.now() is impure, so it can't run directly during render (see the
  // linked purity rule below) -- initialize the ref to null and set the real
  // mount-time baseline in an effect instead, the sanctioned place for
  // one-time impure work. The 15s check interval never fires before this
  // effect runs, so there's no practical gap where a stale/missing value
  // could affect the idle-time calculation.
  const lastActivity = useRef(null);
  const [warning, setWarning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const modalRef = useRef(null);
  const previousFocusRef = useRef(null);

  const handleActivity = useCallback(() => {
    lastActivity.current = Date.now();
    setWarning(false);
  }, []);

  useEffect(() => {
    lastActivity.current = Date.now();
  }, []);

  useEffect(() => {
    if (!warning) {
      if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
        previousFocusRef.current.focus();
      }
      previousFocusRef.current = null;
      return undefined;
    }

    previousFocusRef.current = document.activeElement;

    const timer = setTimeout(() => {
      if (modalRef.current) {
        const focusables = modalRef.current.querySelectorAll('button:not([disabled])');
        if (focusables.length > 0) {
          // Focus the stay signed in confirm button
          const confirmBtn = modalRef.current.querySelector(`.${styles.confirm}`);
          if (confirmBtn) {
            confirmBtn.focus();
          } else {
            focusables[0].focus();
          }
        }
      }
    }, 0);

    const handleKeyDown = (event) => {
      if (event.key === 'Tab' && modalRef.current) {
        const focusables = Array.from(
          modalRef.current.querySelectorAll('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
        );
        if (focusables.length === 0) {
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [warning]);

  useEffect(() => {
    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, handleActivity, { passive: true })
    );
    return () =>
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, handleActivity));
  }, [handleActivity]);

  useEffect(() => {
    const check = () => {
      const idle = Date.now() - lastActivity.current;
      if (idle >= IDLE_TIMEOUT_MS) {
        logout();
        return;
      }
      if (idle >= IDLE_TIMEOUT_MS - WARNING_MS) {
        setWarning(true);
      }
    };
    const timer = window.setInterval(check, CHECK_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [logout]);

  const handleStaySignedIn = async () => {
    setRefreshing(true);
    try {
      await refreshSession();
      handleActivity();
    } finally {
      setRefreshing(false);
    }
  };

  if (!warning) {
    return null;
  }

  return (
    <div className={styles.overlay} role="presentation">
      <div
        ref={modalRef}
        className={styles.modal}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="session-title"
        aria-describedby="session-message"
      >
        <div className={styles.iconWrap} aria-hidden="true">
          <Clock />
        </div>
        <h3 id="session-title" className={styles.title}>
          Your session is about to expire
        </h3>
        <p id="session-message" className={styles.message}>
          You have been inactive for a while. Stay signed in to continue working, or sign out to
          protect the portal.
        </p>
        <div className={styles.actions}>
          <button
            className={styles.cancel}
            type="button"
            disabled={refreshing}
            onClick={logout}
          >
            Sign Out
          </button>
          <button
            className={styles.confirm}
            type="button"
            disabled={refreshing}
            onClick={handleStaySignedIn}
          >
            {refreshing && <Spinner size="small" />}
            Stay Signed In
          </button>
        </div>
      </div>
    </div>
  );
}

export default SessionTimeoutModal;
