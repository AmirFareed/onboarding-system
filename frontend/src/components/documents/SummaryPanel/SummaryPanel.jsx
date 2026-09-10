import { ArrowRight } from 'lucide-react';

import UploadProgress from '../UploadProgress/UploadProgress';
import { computeDocumentProgress } from '../../../data/documents';
import styles from './SummaryPanel.module.css';

/**
 * Right-hand summary panel for the upload page.
 *
 * Tracks how many of the required document copies have been uploaded and gates
 * the "Continue" action until every slot is filled.
 *
 * @param {object} props
 * @param {Array<object>} props.documents Uploaded documents.
 * @param {Function} props.onContinue Callback fired when Continue is clicked.
 */
function SummaryPanel({ documents, onContinue }) {
  const { totalCopies, uploadedCopies, percent } = computeDocumentProgress(documents);
  const remaining = Math.max(0, totalCopies - uploadedCopies);
  const ready = remaining === 0;

  return (
    <aside className={styles.panel}>
      <h3 className={styles.title}>Upload Summary</h3>

      <div className={styles.counts}>
        <div className={styles.count}>
          <span className={styles.countValue}>{uploadedCopies}</span>
          <span className={styles.countLabel}>Uploaded</span>
        </div>
        <div className={styles.count}>
          <span className={styles.countValue}>{remaining}</span>
          <span className={styles.countLabel}>Remaining</span>
        </div>
      </div>

      <UploadProgress progress={percent} label={`${percent}% complete`} />

      <p className={styles.note}>
        {ready
          ? 'All required documents have been uploaded.'
          : `Upload ${remaining} more required copy${remaining === 1 ? '' : 'ies'} to continue.`}
      </p>

      <button
        className={styles.continue}
        type="button"
        disabled={!ready}
        onClick={onContinue}
      >
        Continue to Document Completeness
        <ArrowRight aria-hidden="true" />
      </button>
    </aside>
  );
}

export default SummaryPanel;
