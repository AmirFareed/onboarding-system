import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { FolderPlus } from 'lucide-react';
import { useAuth } from '../../../hooks/useAuth';
import Spinner from '../../common/Spinner/Spinner';
import styles from './ApplicationCard.module.css';

const NOTES_MAX_LENGTH = 2000;

/**
 * Card form used to create a new application.
 *
 * Owns its local field state and reports submission through `onSubmit`. The
 * submit button disables and shows a spinner while `submitting` is true;
 * Cancel returns to the applications list. The creator is always the signed-in
 * employee, shown read-only -- the backend derives it from the session and
 * ignores anything else.
 *
 * @param {object} props
 * @param {boolean} props.submitting Whether a create request is in flight.
 * @param {Function} props.onSubmit Callback with `{notes}`.
 */
function ApplicationCard({ submitting = false, onSubmit }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [notes, setNotes] = useState('');

  const handleSubmit = (event) => {
    event.preventDefault();
    onSubmit({ notes: notes.trim() || null });
  };

  return (
    <form className={styles.card} onSubmit={handleSubmit} noValidate>
      <div className={styles.header}>
        <div className={styles.iconWrap} aria-hidden="true">
          <FolderPlus />
        </div>
        <div>
          <h3 className={styles.title}>Create New Application</h3>
          <p className={styles.subtitle}>Start a new document verification case.</p>
        </div>
      </div>

      <div className={styles.field}>
        <span className={styles.label}>Created By</span>
        <span className={styles.readOnlyValue}>{user?.name}</span>
      </div>

      <label className={styles.field}>
        <span className={styles.label}>Notes</span>
        <textarea
          className={styles.textarea}
          value={notes}
          rows={4}
          placeholder="Optional notes about this application..."
          maxLength={NOTES_MAX_LENGTH}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>

      <div className={styles.actions}>
        <button
          className={styles.secondary}
          type="button"
          onClick={() => navigate('/applications')}
          disabled={submitting}
        >
          Cancel
        </button>
        <button className={styles.submit} type="submit" disabled={submitting}>
          {submitting ? <Spinner /> : <FolderPlus aria-hidden="true" />}
          {submitting ? 'Creating...' : 'Create Application'}
        </button>
      </div>
    </form>
  );
}

export default ApplicationCard;
