import { useState } from 'react';
import { createPortal } from 'react-dom';

import { Eye, Trash2, UploadCloud } from 'lucide-react';
import { Link } from 'react-router-dom';

import ConfirmDialog from '../../common/ConfirmDialog/ConfirmDialog';
import { useToast } from '../../common/Toast/ToastContext';
import { useAuth } from '../../../hooks/useAuth';
import { useApplicationsStore } from '../../../store/ApplicationsContext';
import { canDeleteApplication } from '../../../utils/permissions';
import { formatDate } from '../../../utils/format';
import ApplicationStatusBadge from '../ApplicationStatusBadge/ApplicationStatusBadge';
import styles from './ApplicationRow.module.css';

/**
 * A single application row in the applications table.
 *
 * On mobile the row collapses into a card: the table headers disappear and
 * each cell renders its own `data-label` beside the value, so the table keeps
 * one markup source for every breakpoint.
 *
 * @param {object} props
 * @param {object} props.application Application object to display.
 */
function ApplicationRow({ application }) {
  const { user } = useAuth();
  const { remove } = useApplicationsStore();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    const result = await remove(application.id);
    setDeleting(false);
    setConfirming(false);
    if (result.ok) {
      toast.success(`Application #${application.id} deleted.`);
    } else {
      toast.error(result.error ?? 'Failed to delete application.');
    }
  };

  return (
    <tr className={styles.row}>
      <td className={styles.idCell} data-label="Application ID">
        <Link to={`/applications/${application.id}`} className={styles.idLink}>
          #{application.id}
        </Link>
      </td>
      <td className={styles.nameCell} data-label="Name">
        {application.name ?? <span className={styles.noName}>—</span>}
      </td>
      <td data-label="Status">
        <ApplicationStatusBadge status={application.status} />
      </td>
      <td data-label="Submission Date">{formatDate(application.submitted_at)}</td>
      <td data-label="Last Updated">{formatDate(application.updated_at)}</td>
      <td data-label="Created By">{application.created_by}</td>
      <td className={styles.actionsCell} data-label="Actions">
        <div className={styles.actions}>
          <Link
            to={`/applications/${application.id}`}
            className={styles.actionLink}
            aria-label={`View application ${application.id}`}
          >
            <Eye aria-hidden="true" />
            View
          </Link>
          <Link
            to={`/applications/${application.id}/upload`}
            className={styles.actionLink}
            aria-label={`Upload documents for application ${application.id}`}
          >
            <UploadCloud aria-hidden="true" />
            Upload Documents
          </Link>
          {canDeleteApplication(user) && (
            <button
              type="button"
              className={`${styles.actionLink} ${styles.dangerAction}`}
              aria-label={`Delete application ${application.id}`}
              onClick={() => setConfirming(true)}
            >
              <Trash2 aria-hidden="true" />
              Delete
            </button>
          )}
        </div>
      </td>
      {canDeleteApplication(user) &&
        createPortal(
          <ConfirmDialog
            open={confirming}
            title="Delete this application?"
            message={`This permanently deletes application #${application.id}${
              application.name ? ` (${application.name})` : ''
            } and all of its documents, results and history. This cannot be undone.`}
            confirmLabel="Delete"
            tone="danger"
            loading={deleting}
            onConfirm={handleDelete}
            onCancel={() => setConfirming(false)}
          />,
          document.body
        )}
    </tr>
  );
}

export default ApplicationRow;
