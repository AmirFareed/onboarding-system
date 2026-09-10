import { useCallback, useEffect, useState } from 'react';

import { Check, Pencil, Save } from 'lucide-react';

import {
  getReviewerComments,
  saveReviewerComments,
} from '../../../services/humanReview';
import { useToast } from '../Toast/ToastContext';
import styles from './ReviewerComments.module.css';

const MAX_LENGTH = 5000;

/**
 * Reusable reviewer comments section for Validation Report and Human Review
 * pages. Loads the saved comment on mount, provides an editable textarea,
 * and saves via the shared reviewer-comments API.
 *
 * @param {object} props
 * @param {number|string} props.applicationId Application id.
 * @param {string} [props.defaultComment] Fallback comment when none is saved.
 * @param {string} [props.className] Additional CSS class.
 */
function ReviewerComments({ applicationId, defaultComment = '', className }) {
  const toast = useToast();
  const [comment, setComment] = useState('');
  const [savedComment, setSavedComment] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // react-hooks/set-state-in-effect flags the setState reachable inside
    // the promise chain, but this is an intentional data-fetch-on-mount
    // pattern where the effect itself must initiate the load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    getReviewerComments(applicationId)
      .then((data) => {
        if (cancelled) return;
        const saved = data.reviewer_comments || '';
        setSavedComment(saved);
        setComment(saved || defaultComment);
        setIsEditing(false);
      })
      .catch(() => {
        if (cancelled) return;
        setComment(defaultComment);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [applicationId, defaultComment]);

  const handleSave = useCallback(async () => {
    const trimmed = (comment || '').trim();
    if (trimmed.length > MAX_LENGTH) {
      toast.error(`Comment exceeds ${MAX_LENGTH} character limit.`);
      return;
    }
    setSaving(true);
    try {
      const data = await saveReviewerComments(applicationId, trimmed || null);
      const saved = data.reviewer_comments || '';
      setSavedComment(saved);
      setComment(saved || defaultComment);
      setIsEditing(false);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 3000);
      toast.success('Comment saved.');
    } catch {
      toast.error('Failed to save comment.');
    } finally {
      setSaving(false);
    }
  }, [applicationId, comment, defaultComment, toast]);

  const handleCancel = useCallback(() => {
    setComment(savedComment || defaultComment);
    setIsEditing(false);
  }, [savedComment, defaultComment]);

  const displayComment = savedComment || defaultComment;
  const isDefault = !savedComment;
  const isDirty = (comment || '').trim() !== (savedComment || '').trim();

  if (loading) {
    return (
      <div className={`${styles.container} ${className || ''}`}>
        <div className={styles.header}>
          <h3 className={styles.title}>Reviewer Comments</h3>
        </div>
        <div className={styles.loading}>Loading comment...</div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className || ''}`}>
      <div className={styles.header}>
        <h3 className={styles.title}>Reviewer Comments</h3>
        {!isEditing && (
          <button
            type="button"
            className={styles.editBtn}
            onClick={() => setIsEditing(true)}
          >
            <Pencil aria-hidden="true" size={14} />
            Edit
          </button>
        )}
      </div>

      <p className={styles.hint}>
        Edit this comment before sending the report. This message will be
        visible to the document submitter.
      </p>

      {isEditing ? (
        <div className={styles.editor}>
          <textarea
            className={styles.textarea}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={MAX_LENGTH}
            rows={5}
            placeholder="Enter reviewer comment..."
          />
          <div className={styles.editorFooter}>
            <span className={styles.charCount}>
              {(comment || '').length} / {MAX_LENGTH}
            </span>
            <div className={styles.editorActions}>
              <button
                type="button"
                className={styles.cancelBtn}
                onClick={handleCancel}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                type="button"
                className={styles.saveBtn}
                onClick={handleSave}
                disabled={saving || !isDirty}
              >
                <Save aria-hidden="true" size={14} />
                {saving ? 'Saving...' : 'Save Comment'}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className={styles.display}>
          <div className={styles.commentText}>
            {displayComment || 'No comment saved.'}
          </div>
          {isDefault && (
            <div className={styles.defaultBadge}>Default (auto-generated)</div>
          )}
          {justSaved && (
            <div className={styles.savedBadge}>
              <Check aria-hidden="true" size={14} />
              Comment saved
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ReviewerComments;
