import { useEffect, useRef } from 'react';

import { Download, X } from 'lucide-react';

import styles from './DocumentViewer.module.css';

/**
 * Full-screen modal that renders a document inline via an iframe.
 *
 * The backend /documents/{id}/view endpoint serves the file with
 * Content-Disposition: inline so the browser's built-in viewer renders it
 * (PDF, images, etc.) instead of downloading.
 *
 * @param {object} props
 * @param {boolean} props.open Whether the viewer is visible.
 * @param {string|null} props.viewUrl URL to load in the iframe (inline view).
 * @param {string|null} props.downloadUrl URL for the explicit download action.
 * @param {string} props.title Label shown in the header.
 * @param {Function} props.onClose Callback when the viewer is dismissed.
 */
function DocumentViewer({ open, viewUrl, downloadUrl, title, onClose }) {
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

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  if (!open || !viewUrl) {
    return null;
  }

  return (
    <div className={styles.overlay} role="presentation" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.header}>
          <h3 className={styles.title}>{title}</h3>
          <div className={styles.headerActions}>
            {downloadUrl && (
              <a
                href={downloadUrl}
                className={styles.downloadBtn}
                download
                aria-label={`Download ${title}`}
              >
                <Download aria-hidden="true" />
                Download
              </a>
            )}
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onClose}
              aria-label="Close viewer"
            >
              <X aria-hidden="true" />
            </button>
          </div>
        </div>
        <div className={styles.viewerBody}>
          <iframe
            src={viewUrl}
            className={styles.iframe}
            title={title}
          />
        </div>
      </div>
    </div>
  );
}

export default DocumentViewer;
