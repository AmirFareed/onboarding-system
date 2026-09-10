import { useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { ArrowLeft } from 'lucide-react';

import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import { useToast } from '../../components/common/Toast/ToastContext';
import BulkUploadZone from '../../components/documents/BulkUploadZone/BulkUploadZone';
import SummaryPanel from '../../components/documents/SummaryPanel/SummaryPanel';
import { useDocuments } from '../../hooks/useDocuments';
import { getPreference } from '../../utils/preferences';
import { startProcessing } from '../../services/processing';
import styles from './UploadDocumentsPage.module.css';

/**
 * Document upload page for one application.
 *
 * The combined-PDF bulk dropzone is the only way to get documents onto an
 * application from this page; the backend splits it into the individual
 * checklist documents automatically. Right column shows upload progress
 * against the required checklist throughout.
 */
function UploadDocumentsPage() {
  const { applicationId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();

  const { documents, loading, error, reload, pending, uploadBulk } = useDocuments(applicationId);

  const pendingBulkDocument = documents?.find(
    (d) => d.document_type === 'BULK_UPLOAD' && d.processing_status !== 'COMPLETED'
  );

  useEffect(() => {
    if (pendingBulkDocument) {
      const timer = setInterval(() => {
        reload();
      }, 5000);
      return () => clearInterval(timer);
    }
  }, [pendingBulkDocument, reload]);

  const maybeAutoStartProcessing = () => {
    if (!getPreference('autoStartProcessingAfterUpload', true)) {
      return;
    }
    startProcessing(applicationId).catch(() => {
      // Best effort: a processing failure should never surface as an upload error.
    });
  };

  const handleBulkUpload = async (file) => {
    const result = await uploadBulk(file);
    if (result.ok) {
      toast.success('Bulk PDF uploaded and split successfully.');
      maybeAutoStartProcessing();
    } else {
      toast.error(result.error);
    }
  };

  if (loading) {
    return (
      <div className={styles.center} aria-busy="true">
        <Spinner size="medium" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <Link to={`/applications/${applicationId}`} className={styles.backLink}>
        <ArrowLeft aria-hidden="true" />
        Back to Application #{applicationId}
      </Link>

      <header className={styles.header}>
        <h2 className={styles.title}>Upload Documents</h2>
        <p className={styles.subtitle}>
          Attach the required files for application #{applicationId}.
        </p>
      </header>

      {error ? (
        <ErrorState message="Unable to load documents." onRetry={reload} />
      ) : (
        <div className={styles.layout}>
          <div className={styles.main}>
            {pendingBulkDocument ? (
              <div className={styles.processingBanner}>
                <Spinner size="small" />
                <p>Your combined PDF is being split and analyzed in the background. This may take a few minutes...</p>
              </div>
            ) : (
              <BulkUploadZone onUpload={handleBulkUpload} pending={pending['upload-bulk']} />
            )}
          </div>

          <SummaryPanel documents={documents} onContinue={() => navigate('/completeness')} />
        </div>
      )}
    </div>
  );
}

export default UploadDocumentsPage;
