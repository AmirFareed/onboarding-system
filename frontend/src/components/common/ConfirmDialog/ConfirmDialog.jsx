import { useEffect, useRef } from 'react';

import { AlertTriangle } from 'lucide-react';
import Spinner from '../Spinner/Spinner';
import styles from './ConfirmDialog.module.css';

/**
 * Confirmation modal used before destructive actions (delete, replace).
 *
 * Renders nothing when closed. While `loading` is true the confirm button shows
 * a spinner and both actions are disabled. Pressing Escape cancels.
 *
 * @param {object} props
 * @param {boolean} props.open Whether the dialog is visible.
 * @param {string} props.title Heading text.
 * @param {string} props.message Body text.
 * @param {string} [props.confirmLabel] Confirm button label.
 * @param {string} [props.cancelLabel] Cancel button label.
 * @param {string} [props.tone] Visual tone: "danger" or "primary".
 * @param {boolean} [props.loading] Whether an action is in flight.
 * @param {Function} props.onConfirm Callback when confirmed.
 * @param {Function} props.onCancel Callback when dismissed.
 */
function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  loading = false,
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (!open) {
      if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
        previousFocusRef.current.focus();
      }
      previousFocusRef.current = null;
      return undefined;
    }

    previousFocusRef.current = document.activeElement;

    // Focus the first focusable button inside the dialog on mount
    const timer = setTimeout(() => {
      if (dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll('button:not([disabled])');
        if (focusables.length > 0) {
          focusables[0].focus();
        }
      }
    }, 0);

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !loading) {
        onCancel();
        return;
      }

      if (event.key === 'Tab' && dialogRef.current) {
        const focusables = Array.from(
          dialogRef.current.querySelectorAll('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
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
  }, [open, loading, onCancel]);

  if (!open) {
    return null;
  }

  return (
    <div className={styles.overlay} role="presentation" onMouseDown={onCancel}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.iconWrap} aria-hidden="true">
          <AlertTriangle />
        </div>
        <h3 id="confirm-title" className={styles.title}>
          {title}
        </h3>
        <p id="confirm-message" className={styles.message}>
          {message}
        </p>
        <div className={styles.actions}>
          <button
            className={styles.cancel}
            type="button"
            disabled={loading}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            className={`${styles.confirm} ${tone === 'danger' ? styles.danger : styles.primary}`}
            type="button"
            disabled={loading}
            onClick={onConfirm}
          >
            {loading && <Spinner size="small" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;
