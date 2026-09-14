import { Play, RotateCcw, Square } from 'lucide-react';

import BatchUploadZone from '../../components/documents/BatchUploadZone/BatchUploadZone';
import BatchUploadQueueTable from '../../components/documents/BatchUploadQueueTable/BatchUploadQueueTable';
import { useToast } from '../../components/common/Toast/ToastContext';
import { useBatchUploadStore } from '../../store/BatchUploadContext';
import styles from './BatchUploadPage.module.css';

/**
 * Batch PDF upload page.
 *
 * Lets an operator select many separate PDFs (30+) in one action. Each file
 * becomes its own application, named automatically from its filename, and
 * is processed one at a time -- created, uploaded, started, then watched
 * until it completes or fails -- before the next queued file begins. State
 * lives in BatchUploadContext (mounted at the app root), so this page is a
 * thin view: it can be left and re-opened without losing progress.
 */
function BatchUploadPage() {
  const toast = useToast();
  const { items, counts, running, addFiles, removeFile, start, cancel, reset } =
    useBatchUploadStore();

  const handleFilesSelected = (fileList) => {
    const { addedCount, skippedCount } = addFiles(fileList);
    if (skippedCount > 0) {
      toast.error(
        `${skippedCount} file${skippedCount === 1 ? '' : 's'} skipped (not a PDF).`
      );
    }
    if (addedCount > 0) {
      toast.success(
        `${addedCount} PDF${addedCount === 1 ? '' : 's'} added to the queue.`
      );
    } else if (skippedCount === 0) {
      toast.error('No files were selected.');
    }
  };

  const handleStart = async () => {
    const { remainingMissingFileCount } = await start();
    if (remainingMissingFileCount > 0) {
      toast.error(
        `${remainingMissingFileCount} file${remainingMissingFileCount === 1 ? '' : 's'} ` +
          `still need${remainingMissingFileCount === 1 ? 's' : ''} to be re-added before ` +
          `${remainingMissingFileCount === 1 ? 'it' : 'they'} can process -- their file didn't ` +
          `survive a page reload. Remove and re-add ${remainingMissingFileCount === 1 ? 'it' : 'them'} below.`
      );
    }
  };

  const canReset = !running && items.length > 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Batch Upload PDFs</h2>
        <p className={styles.subtitle}>
          Select multiple combined onboarding PDFs at once. Each one becomes its own application,
          processed automatically one at a time.
        </p>
      </header>

      <BatchUploadZone onFilesSelected={handleFilesSelected} disabled={running} />

      <div className={styles.summaryBar}>
        <div className={styles.counts}>
          <span className={styles.countItem}>
            <strong>{counts.total}</strong> total
          </span>
          <span className={styles.countItem}>
            <strong>{counts.pending}</strong> pending
          </span>
          <span className={styles.countItem}>
            <strong>{counts.processing}</strong> processing
          </span>
          <span className={styles.countItem}>
            <strong>{counts.completed}</strong> completed
          </span>
          <span className={styles.countItem}>
            <strong>{counts.failed}</strong> failed
          </span>
          {counts.needsFile > 0 && (
            <span className={styles.countItemWarning}>
              <strong>{counts.needsFile}</strong> need file re-added
            </span>
          )}
        </div>
        <div className={styles.controls}>
          {running ? (
            <button type="button" className={styles.secondaryBtn} onClick={cancel}>
              <Square aria-hidden="true" />
              Stop After Current File
            </button>
          ) : (
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={handleStart}
              disabled={counts.pending === 0}
            >
              <Play aria-hidden="true" />
              {counts.completed + counts.failed > 0 ? 'Resume' : 'Start Processing'}
            </button>
          )}
          <button
            type="button"
            className={styles.secondaryBtn}
            onClick={reset}
            disabled={!canReset}
          >
            <RotateCcw aria-hidden="true" />
            Clear Queue
          </button>
        </div>
      </div>

      <BatchUploadQueueTable items={items} onRemove={removeFile} />
    </div>
  );
}

export default BatchUploadPage;
