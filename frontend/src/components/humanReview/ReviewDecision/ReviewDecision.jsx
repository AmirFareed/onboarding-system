import { useState } from 'react';

import { AlertTriangle, Check, FileText, Send, X } from 'lucide-react';

import { getDocumentLabel } from '../../../utils/validationSemantic';
import styles from './ReviewDecision.module.css';

const DECISIONS = [
  {
    value: 'APPROVE',
    label: 'Approve',
    description: 'Approves the application when all blocking issues are resolved.',
  },
  {
    value: 'CONDITIONAL_APPROVE',
    label: 'Conditional Approval',
    description: 'Approves subject to explicitly recorded conditions. Bypasses normal approval blocking.',
  },
  {
    value: 'CORRECT',
    label: 'Correct',
    description: 'Records corrected field values and marks the application as corrected.',
  },
  {
    value: 'REJECT',
    label: 'Reject',
    description: 'Rejects the application. A rejection reason is required.',
  },
];

const SUBMIT_LABELS = {
  APPROVE: 'Submit Approval',
  CONDITIONAL_APPROVE: 'Confirm Conditional Approval',
  CORRECT: 'Submit Correction',
  REJECT: 'Confirm Rejection',
};

/**
 * Final decision form for the Human Review page.
 *
 * Shows approval gating with clear blocking issues, Request Missing Documents
 * action, correction summary, and conditional approval workflow.
 *
 * @param {object} props
 * @param {string} props.reviewerName Current reviewer name.
 * @param {string} props.decision Selected decision value.
 * @param {Function} props.onDecisionChange Decision handler.
 * @param {string} props.comments Review comments.
 * @param {Function} props.onCommentsChange Comments handler.
 * @param {string} props.rejectionReason Rejection reason.
 * @param {Function} props.onRejectionReasonChange Rejection reason handler.
 * @param {object[]} props.checklist Checklist items with state.
 * @param {object[]} props.corrections Field corrections.
 * @param {object} props.approvalBlocking Blocking issues from view model.
 * @param {string[]} props.requestableDocTypes Missing document types.
 * @param {Function} props.onRequestMissingDocs Handler for requesting missing docs.
 * @param {boolean} props.submitting Submission in progress.
 * @param {boolean} props.readOnly Disable the form.
 * @param {string|null} props.submitError Server-side error message.
 * @param {Function} props.onSubmit Payload submit handler.
 * @param {string} props.condition Conditional approval condition text.
 * @param {Function} props.onConditionChange Condition handler.
 * @param {string} props.dueDate Conditional approval due date.
 * @param {Function} props.onDueDateChange Due date handler.
 * @param {string} props.additionalComments Conditional approval additional comments.
 * @param {Function} props.onAdditionalCommentsChange Additional comments handler.
 */
function ReviewDecision({
  reviewerName,
  decision,
  onDecisionChange,
  comments,
  onCommentsChange,
  rejectionReason,
  onRejectionReasonChange,
  checklist,
  corrections,
  approvalBlocking,
  requestableDocTypes,
  onRequestMissingDocs,
  submitting,
  readOnly,
  submitError,
  onSubmit,
  condition,
  onConditionChange,
  dueDate,
  onDueDateChange,
  additionalComments,
  onAdditionalCommentsChange,
}) {
  const [showMissingDocsModal, setShowMissingDocsModal] = useState(false);

  const hasCorrection = corrections.some((correction) => (correction.corrected_value ?? '').trim());

  // Determine validation error based on decision
  let validationError = null;
  if (!reviewerName) {
    validationError = 'Your reviewer name could not be determined. Contact your administrator.';
  } else if (!decision) {
    validationError = 'Choose a decision to continue.';
  } else if (decision === 'APPROVE') {
    if (!approvalBlocking) {
      validationError = 'Loading approval status...';
    } else if (approvalBlocking.blocked) {
      const parts = [];
      if (approvalBlocking.failures > 0) {
        parts.push(
          `${approvalBlocking.failures} validation failure${approvalBlocking.failures > 1 ? 's' : ''}`
        );
      }
      if (approvalBlocking.uncheckedActionable > 0) {
        parts.push(
          `${approvalBlocking.uncheckedActionable} actionable review item${approvalBlocking.uncheckedActionable > 1 ? 's' : ''} not confirmed`
        );
      }
      if (parts.length > 0) {
        validationError = `Approval blocked: ${parts.join(' and ')}.`;
      }
    }
  } else if (decision === 'CONDITIONAL_APPROVE') {
    if (!condition.trim()) {
      validationError = 'A condition or required action is mandatory for conditional approval.';
    } else {
      validationError =
        'Conditional Approval is not yet supported by the backend API. The ReviewDecision enum only accepts APPROVE, CORRECT, REJECT. Contact engineering to add CONDITIONAL_APPROVE support.';
    }
  } else if (decision === 'CORRECT' && !hasCorrection) {
    validationError = 'Add at least one field correction to correct.';
  } else if (decision === 'REJECT' && !rejectionReason.trim()) {
    validationError = 'A rejection reason is required to reject.';
  }

  const handleSubmit = () => {
    if (validationError || submitting || readOnly) return;

    // CONDITIONAL_APPROVE is not sent to the backend — the API does not
    // support it yet. The validation error above prevents reaching here.
    if (decision === 'CONDITIONAL_APPROVE') return;

    onSubmit({
      reviewer_name: reviewerName,
      decision,
      comments: comments.trim() ? comments : null,
      rejection_reason: decision === 'REJECT' ? rejectionReason.trim() : null,
      checklist: checklist.map((item) => ({
        item_name: item.itemName,
        is_checked: item.is_checked,
      })),
      corrections: corrections
        .filter((correction) => (correction.corrected_value ?? '').trim())
        .map((correction) => ({
          field_name: correction.field_name,
          document_id: correction.document_id ?? null,
          corrected_value: correction.corrected_value.trim(),
          reason: (correction.reason ?? '').trim() || null,
        })),
    });
  };

  const submitLabel = SUBMIT_LABELS[decision] || 'Submit decision';

  return (
    <div className={styles.panel}>
      {/* Blocking issues */}
      {approvalBlocking && approvalBlocking.blocked && decision === 'APPROVE' && (
        <div className={styles.blockingSection}>
          <div className={styles.blockingHeader}>
            <AlertTriangle className={styles.blockingIcon} aria-hidden="true" />
            <span className={styles.blockingTitle}>Approval Blocked</span>
          </div>
          <ul className={styles.blockingList}>
            {approvalBlocking.failures > 0 && (
              <li>
                {approvalBlocking.failures} validation failure{approvalBlocking.failures > 1 ? 's' : ''}
              </li>
            )}
            {approvalBlocking.missingDocs > 0 && (
              <li>
                {approvalBlocking.missingDocs} missing required document{approvalBlocking.missingDocs > 1 ? 's' : ''}
              </li>
            )}
            {approvalBlocking.uncheckedActionable > 0 && (
              <li>
                {approvalBlocking.uncheckedActionable} actionable review item{approvalBlocking.uncheckedActionable > 1 ? 's' : ''} not confirmed
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Decision options */}
      <div className={styles.decisions}>
        {DECISIONS.map((option) => (
          <label
            key={option.value}
            className={`${styles.option} ${decision === option.value ? styles.optionActive : ''}`}
          >
            <input
              type="radio"
              name="review-decision"
              value={option.value}
              className={styles.radio}
              checked={decision === option.value}
              disabled={readOnly}
              onChange={() => onDecisionChange(option.value)}
            />
            <span className={styles.optionLabel}>{option.label}</span>
            <span className={styles.optionDescription}>{option.description}</span>
          </label>
        ))}
      </div>

      {/* Conditional Approval form — inline below the decision grid */}
      {decision === 'CONDITIONAL_APPROVE' && (
        <div className={styles.conditionalForm}>
          <label className={styles.conditionalField}>
            <span className={styles.conditionalLabel}>Condition / Required Action (required)</span>
            <textarea
              className={styles.conditionalTextarea}
              rows="3"
              value={condition}
              disabled={readOnly}
              onChange={(event) => onConditionChange(event.target.value)}
              placeholder="e.g. Submit the missing Bilateral Agreement and Tripartite Agreement before final processing."
            />
          </label>
          <label className={styles.conditionalField}>
            <span className={styles.conditionalLabel}>Due Date (optional)</span>
            <input
              type="date"
              className={styles.conditionalDate}
              value={dueDate}
              disabled={readOnly}
              onChange={(event) => onDueDateChange(event.target.value)}
            />
          </label>
          <label className={styles.conditionalField}>
            <span className={styles.conditionalLabel}>Additional Comments (optional)</span>
            <textarea
              className={styles.conditionalTextarea}
              rows="2"
              value={additionalComments}
              disabled={readOnly}
              onChange={(event) => onAdditionalCommentsChange(event.target.value)}
              placeholder="Any additional notes for this conditional approval."
            />
          </label>
        </div>
      )}

      {/* Request Missing Documents button */}
      {requestableDocTypes && requestableDocTypes.length > 0 && (
        <div className={styles.missingDocsAction}>
          <button
            type="button"
            className={styles.missingDocsBtn}
            onClick={() => setShowMissingDocsModal(true)}
          >
            <FileText aria-hidden="true" />
            Request Missing Documents ({requestableDocTypes.length})
          </button>
        </div>
      )}

      {/* Corrections summary */}
      {corrections.length > 0 && (
        <div className={styles.correctionsSummary}>
          <span className={styles.correctionsTitle}>
            {corrections.length} field correction{corrections.length !== 1 ? 's' : ''} recorded
          </span>
          <ul className={styles.correctionsList}>
            {corrections.map((correction) => (
              <li key={`${correction.document_id}::${correction.field_name}`} className={styles.correctionItem}>
                <span className={styles.correctionField}>{correction.field_name}</span>
                {correction.corrected_value && (
                  <span className={styles.correctionValue}>
                    → <strong>{correction.corrected_value}</strong>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Comments */}
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Comments (optional)</span>
        <textarea
          className={styles.textarea}
          rows="3"
          value={comments}
          disabled={readOnly}
          onChange={(event) => onCommentsChange(event.target.value)}
          placeholder="Notes for the review record"
        />
      </label>

      {/* Rejection reason */}
      {decision === 'REJECT' && (
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Rejection reason (required)</span>
          <textarea
            className={`${styles.textarea} ${styles.reason}`}
            rows="2"
            value={rejectionReason}
            disabled={readOnly}
            onChange={(event) => onRejectionReasonChange(event.target.value)}
            placeholder="Explain why the application is rejected"
          />
        </label>
      )}

      {/* Validation error */}
      {validationError && (
        <div className={styles.validationError} role="alert">
          <AlertTriangle className={styles.errorIcon} aria-hidden="true" />
          {validationError}
        </div>
      )}

      {/* Submit error */}
      {submitError && (
        <div className={styles.submitError} role="alert">
          <AlertTriangle className={styles.errorIcon} aria-hidden="true" />
          {submitError}
        </div>
      )}

      {/* Submit button */}
      {!readOnly && (
        <button
          type="button"
          className={styles.submitBtn}
          disabled={Boolean(validationError) || submitting}
          onClick={handleSubmit}
        >
          {submitting ? (
            <>
              <Send className={styles.submitIcon} aria-hidden="true" />
              Submitting…
            </>
          ) : (
            <>
              <Check className={styles.submitIcon} aria-hidden="true" />
              {submitLabel}
            </>
          )}
        </button>
      )}

      {/* Missing Documents Modal */}
      {showMissingDocsModal && (
        <div className={styles.modalOverlay} onClick={() => setShowMissingDocsModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>Request Missing Documents</h3>
              <button
                type="button"
                className={styles.modalClose}
                onClick={() => setShowMissingDocsModal(false)}
                aria-label="Close"
              >
                <X aria-hidden="true" />
              </button>
            </div>
            <div className={styles.modalBody}>
              <p className={styles.modalDescription}>
                The following required documents are missing. A request will be sent
                to the applicant to provide them.
              </p>
              <ul className={styles.modalDocList}>
                {requestableDocTypes.map((docType) => (
                  <li key={docType} className={styles.modalDocItem}>
                    {getDocumentLabel(docType)}
                  </li>
                ))}
              </ul>
            </div>
            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.modalCancel}
                onClick={() => setShowMissingDocsModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className={styles.modalConfirm}
                onClick={() => {
                  setShowMissingDocsModal(false);
                  onRequestMissingDocs(requestableDocTypes);
                }}
              >
                Send Request
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ReviewDecision;
