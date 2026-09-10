import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentTypeConfig } from '../../../data/documents';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewDetections.module.css';

/**
 * Signature and stamp visual detection findings.
 *
 * Shows semantic counts derived from the shared visual model, plus
 * individual detection items for manual review.
 *
 * @param {object} props
 * @param {object} props.viewModel Derived semantic state.
 * @param {object[]} props.detections Raw detection items from reviewScreen.
 */
function ReviewDetections({ viewModel, detections }) {
  const { visual } = viewModel;

  const hasDetections = detections && detections.length > 0;
  const hasVisualData =
    visual.signatures.present > 0 ||
    visual.signatures.missing > 0 ||
    visual.signatures.pending > 0 ||
    visual.signatures.notVerifiable > 0 ||
    visual.stamps.present > 0 ||
    visual.stamps.missing > 0 ||
    visual.stamps.pending > 0 ||
    visual.stamps.notVerifiable > 0;

  return (
    <div className={styles.container}>
      {/* Signature summary */}
      <div className={styles.summaryCard}>
        <h4 className={styles.summaryTitle}>Signature Verification</h4>
        <div className={styles.summaryCounts}>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.present}`} />
            {visual.signatures.present} Present
          </span>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.missing}`} />
            {visual.signatures.missing} Missing
          </span>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.pending}`} />
            {visual.signatures.pending} Pending
          </span>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.notVerifiable}`} />
            {visual.signatures.notVerifiable} Not Verifiable
          </span>
        </div>
      </div>

      {/* Stamp summary */}
      <div className={styles.summaryCard}>
        <h4 className={styles.summaryTitle}>Stamp Verification</h4>
        <div className={styles.summaryCounts}>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.present}`} />
            {visual.stamps.present} Present
          </span>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.missing}`} />
            {visual.stamps.missing} Missing
          </span>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.pending}`} />
            {visual.stamps.pending} Pending
          </span>
          <span className={styles.countItem}>
            <span className={`${styles.countDot} ${styles.notVerifiable}`} />
            {visual.stamps.notVerifiable} Not Verifiable
          </span>
        </div>
      </div>

      {/* Individual detections */}
      {hasDetections && (
        <div className={styles.detectionsSection}>
          <h4 className={styles.sectionTitle}>Detection Details</h4>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Document</th>
                <th scope="col">Detection</th>
                <th scope="col">Result</th>
                <th scope="col">Confidence</th>
                <th scope="col">Detected</th>
              </tr>
            </thead>
            <tbody>
              {detections.map((detection) => {
                const config = getDocumentTypeConfig(detection.document_type);
                return (
                  <tr key={`${detection.document_id}-${detection.detection_type}`}>
                    <td data-label="Document" className={styles.typeCell}>
                      {config.label}
                    </td>
                    <td data-label="Detection" className={styles.mutedCell}>
                      {detection.detection_type === 'signature' ? 'Signature' : 'Stamp'}
                    </td>
                    <td data-label="Result">
                      <StatusChip
                        label={detection.is_present ? 'Present' : 'Missing'}
                        variant={detection.is_present ? 'success' : 'danger'}
                      />
                    </td>
                    <td data-label="Confidence" className={styles.mutedCell}>
                      {detection.confidence != null
                        ? `${Math.round(detection.confidence * 100)}%`
                        : '—'}
                    </td>
                    <td data-label="Detected" className={styles.mutedCell}>
                      {formatDateTime(detection.detected_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Explanation of states */}
      {!hasVisualData && !hasDetections && (
        <p className={styles.empty}>
          No signature or stamp detections are available for this application.
        </p>
      )}

      <div className={styles.explanations}>
        <div className={styles.explanation}>
          <strong>Pending</strong> — Document exists, but automated detection has not completed.
        </div>
        <div className={styles.explanation}>
          <strong>Not Verifiable</strong> — The required document is missing, so this check
          cannot currently be performed.
        </div>
      </div>
    </div>
  );
}

export default ReviewDetections;
