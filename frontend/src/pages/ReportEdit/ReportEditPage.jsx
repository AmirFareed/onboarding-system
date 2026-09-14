import { useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Save, X } from 'lucide-react';

import ConfirmDialog from '../../components/common/ConfirmDialog/ConfirmDialog';
import { useToast } from '../../components/common/Toast/ToastContext';
import {
  downloadValidationReportPdf,
  getValidationReportHtmlUrl,
  saveEditedReportHtml,
} from '../../services/reports';
import { getApiErrorMessage } from '../../utils/apiError';
import styles from './ReportEditPage.module.css';

/**
 * Edit view for the printable validation report.
 *
 * Loads the same HTML the report's own "View / Print Report" link and PDF
 * download render from (backend/app/reports/services.py's render_html())
 * into an iframe, then turns the whole iframe document editable via the
 * browser's native ``designMode`` -- real rich-text editing (typing,
 * formatting, table edits) with no editor library needed, and no risk of
 * the report's own print CSS colliding with the app's styles, since an
 * iframe is a fully separate document.
 *
 * Saving PUTs the edited HTML to the backend (see
 * services/reports.js::saveEditedReportHtml), which becomes what every
 * future view/download of this report serves until edited again -- see
 * ValidationReportService.render_html()'s edited_report_html check. After
 * a successful save, offers to download the PDF immediately so the
 * reviewer doesn't have to navigate back and re-open it separately.
 */
function ReportEditPage() {
  const { applicationId } = useParams();
  const toast = useToast();
  const iframeRef = useRef(null);
  const [iframeLoading, setIframeLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirmDownload, setConfirmDownload] = useState(false);

  const reportUrl = getValidationReportHtmlUrl(applicationId);

  const handleIframeLoad = () => {
    const doc = iframeRef.current?.contentDocument;
    if (doc) {
      doc.designMode = 'on';
    }
    setIframeLoading(false);
  };

  const handleSave = async () => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc?.documentElement) {
      return;
    }
    const html = `<!DOCTYPE html>\n${doc.documentElement.outerHTML}`;
    setSaving(true);
    try {
      await saveEditedReportHtml(applicationId, html);
      toast.success('Report saved.');
      setConfirmDownload(true);
    } catch (err) {
      toast.error(getApiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = async () => {
    setConfirmDownload(false);
    try {
      await downloadValidationReportPdf(applicationId);
    } catch {
      toast.error('Failed to download PDF. Please try again.');
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Edit Validation Report</h2>
          <p className={styles.subtitle}>
            Click directly into the report below to make changes, then save. Saved changes
            replace what every future view and PDF download of this report shows.
          </p>
        </div>
        <div className={styles.actions}>
          <Link
            to={`/reports?application=${applicationId}`}
            className={styles.cancelBtn}
          >
            <X aria-hidden="true" />
            Cancel
          </Link>
          <button
            type="button"
            className={styles.saveBtn}
            onClick={handleSave}
            disabled={saving || iframeLoading}
          >
            <Save aria-hidden="true" />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </header>

      <div className={styles.iframeWrap}>
        <iframe
          ref={iframeRef}
          src={reportUrl}
          title="Edit validation report"
          className={styles.iframe}
          onLoad={handleIframeLoad}
        />
      </div>

      <ConfirmDialog
        open={confirmDownload}
        title="Report saved"
        message="Your edited report has been saved. Download the PDF now?"
        confirmLabel="Download PDF"
        cancelLabel="Not now"
        tone="primary"
        onConfirm={handleDownload}
        onCancel={() => setConfirmDownload(false)}
      />
    </div>
  );
}

export default ReportEditPage;
