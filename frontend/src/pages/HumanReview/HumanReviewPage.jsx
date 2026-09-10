import { useEffect, useState } from 'react';

import { Info, RefreshCw } from 'lucide-react';

import ConfirmDialog from '../../components/common/ConfirmDialog/ConfirmDialog';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import ReviewerComments from '../../components/common/ReviewerComments/ReviewerComments';
import { useToast } from '../../components/common/Toast/ToastContext';
import ReviewChecklist from '../../components/humanReview/ReviewChecklist/ReviewChecklist';
import ReviewDecision from '../../components/humanReview/ReviewDecision/ReviewDecision';
import ReviewDetections from '../../components/humanReview/ReviewDetections/ReviewDetections';
import ReviewDocuments from '../../components/humanReview/ReviewDocuments/ReviewDocuments';
import ReviewFields from '../../components/humanReview/ReviewFields/ReviewFields';
import ReviewHistory from '../../components/humanReview/ReviewHistory/ReviewHistory';
import ReviewSummary from '../../components/humanReview/ReviewSummary/ReviewSummary';
import { APPLICATION_STATUSES } from '../../data/statuses';
import { useAuth } from '../../hooks/useAuth';
import { useHumanReview } from '../../hooks/useHumanReview';
import { useHumanReviewViewModel } from '../../hooks/useHumanReviewViewModel';
import { getDocumentDownloadUrl, getDocumentViewUrl } from '../../services/documents';
import { getPreference } from '../../utils/preferences';
import styles from './HumanReviewPage.module.css';

function Section({ title, children, note }) {
  return (
    <section className={styles.section} aria-label={title}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>{title}</h3>
      </div>
      {note && <p className={styles.sectionNote}>{note}</p>}
      {children}
    </section>
  );
}

function ReviewSkeleton() {
  return (
    <div aria-hidden="true">
      <div className={styles.skeletonHeader} />
      <div className={styles.skeletonTable} />
    </div>
  );
}

/**
 * Final human review workflow.
 *
 * Opens the stored review screen for a selected application and lets the
 * reviewer drive the final decision (approve / correct / reject) against the
 * full checklist, field corrections, documents, OCR state and signature/stamp
 * findings. An application can only be reviewed once: when a previous review
 * exists the page is read-only and shows the stored decision.
 */
function HumanReviewPage() {
  const { user } = useAuth();
  const {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange,
    selectedId,
    onSelect,
    reviewScreen,
    history,
    loading,
    error,
    submitting,
    submitError,
    submit,
    alreadyReviewed,
    onRefresh,
  } = useHumanReview();
  const toast = useToast();

  // Derive semantic state from review screen (same logic as Validation Report)
  const viewModel = useHumanReviewViewModel(reviewScreen);

  const reviewerName = user?.name ?? '';

  const [decision, setDecision] = useState('');
  const [comments, setComments] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [checklist, setChecklist] = useState({});
  const [corrections, setCorrections] = useState([]);
  const [pendingRejectPayload, setPendingRejectPayload] = useState(null);
  const [condition, setCondition] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [additionalComments, setAdditionalComments] = useState('');
  const [amcViewed, setAmcViewed] = useState(false);

  // Reset the review form whenever the selected queue row changes
  const [resetForSelectedId, setResetForSelectedId] = useState(selectedId);
  if (selectedId !== resetForSelectedId) {
    setResetForSelectedId(selectedId);
    setDecision('');
    setComments('');
    setRejectionReason('');
    setCorrections([]);
    setCondition('');
    setDueDate('');
    setAdditionalComments('');
    setAmcViewed(false);
  }

  // Build checklist state from derived requirements.
  // Use the raw backend checklist as the stable dependency — the derived
  // requirements are a new array reference every render, which would cause
  // infinite re-renders with the render-time comparison pattern.
  const checklistRequirements = viewModel?.checklistRequirements ?? [];
  const rawChecklistSource = reviewScreen?.checklist;

  // Reset checklist state when the raw backend checklist changes (new selection or new data).
  // The render-time comparison pattern causes infinite re-renders because derived
  // requirements are a new array reference every render. Using useEffect with the
  // raw backend checklist (stable reference from API) is the safe alternative.
  useEffect(() => {
    if (!rawChecklistSource) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setChecklist(
      checklistRequirements.reduce((acc, item) => {
        acc[item.itemName] = item.is_checked;
        return acc;
      }, {})
    );
    // Only reset when the raw checklist reference changes (new selection).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawChecklistSource]);

  const checklistWithState = checklistRequirements.map((item) => ({
    ...item,
    is_checked: Boolean(checklist[item.itemName]),
  }));

  // Find the AMC document for the View→Confirm workflow
  const amcDocument = reviewScreen?.documents?.find(
    (doc) => doc.document_type === 'ACCOUNT_MAINTENANCE_CERTIFICATE'
  );
  const amcViewUrl = amcDocument
    ? getDocumentViewUrl(selectedId, amcDocument.document_id)
    : null;
  const amcDownloadUrl = amcDocument
    ? getDocumentDownloadUrl(selectedId, amcDocument.document_id)
    : null;

  const handleAmcView = () => {
    setAmcViewed(true);
  };

  const toggleChecklist = (itemName) => {
    setChecklist((prev) => ({ ...prev, [itemName]: !prev[itemName] }));
  };

  const handleSubmit = async (payload) => {
    if (payload.decision === 'REJECT' && getPreference('confirmBeforeRejectApplication', true)) {
      setPendingRejectPayload(payload);
      return;
    }
    await submitReview(payload);
  };

  const submitReview = async (payload) => {
    const result = await submit(payload);
    if (result) {
      toast.success('Final review submitted successfully.');
      setDecision('');
      setComments('');
      setRejectionReason('');
      setCorrections([]);
      setCondition('');
      setDueDate('');
      setAdditionalComments('');
    }
  };

  const handleRejectConfirmed = () => {
    const payload = pendingRejectPayload;
    setPendingRejectPayload(null);
    if (payload) {
      void submitReview(payload);
    }
  };

  const handleRequestMissingDocs = (docTypes) => {
    toast.success(`Document request sent for ${docTypes.length} document(s).`);
  };

  const readOnly = alreadyReviewed;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Human Review</h2>
        <p className={styles.subtitle}>
          Record the final decision for an application after reviewing its documents, extracted
          fields and verification findings.
        </p>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.filter} htmlFor="review-app-select">
          <span className={styles.filterLabel}>Application</span>
          <select
            id="review-app-select"
            className={styles.select}
            value={selectedId ?? ''}
            onChange={(event) => onSelect(event.target.value)}
            aria-label="Select an application to review"
            disabled={appsLoading}
          >
            <option value="">Select an application</option>
            {applications.map((app) => (
              <option key={app.id} value={app.id}>
                #{app.id} — {app.name || app.created_by} ({app.status})
              </option>
            ))}
          </select>
        </label>

        <label className={styles.filter} htmlFor="review-status-filter">
          <span className={styles.filterLabel}>Status</span>
          <select
            id="review-status-filter"
            className={styles.select}
            value={statusFilter}
            onChange={(event) => onStatusChange(event.target.value)}
            aria-label="Filter applications by status"
          >
            <option value="">All</option>
            {APPLICATION_STATUSES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <button type="button" className={styles.secondaryBtn} onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </div>

      {appsError && <ErrorState message={appsError} onRetry={onRefresh} />}

      {selectedId == null && !appsError && (
        <EmptyState
          title="Select an application"
          message="Choose an application above to open its final review."
        />
      )}

      {selectedId != null && loading && <ReviewSkeleton />}

      {selectedId != null && !loading && error && (
        <ErrorState message={error} onRetry={onRefresh} />
      )}

      {selectedId != null && !loading && !error && reviewScreen && viewModel && (
        <>
          {/* 1. Application Header */}
          <ReviewSummary viewModel={viewModel} />

          {readOnly && (
            <div className={styles.readOnlyBanner} role="status">
              <Info className={styles.bannerIcon} aria-hidden="true" />
              <div>
                <strong>This application has already been finally reviewed.</strong>
                <p>
                  The decision below is the stored record. No further review can be submitted for
                  this application.
                </p>
              </div>
            </div>
          )}

          {/* 2. Documents */}
          <Section title="Documents">
            <ReviewDocuments
              viewModel={viewModel}
              uploadedDocuments={reviewScreen.documents}
            />
          </Section>

          {/* 3. Extracted Fields */}
          <Section
            title="Extracted Fields"
            note={
              readOnly
                ? 'Stored extracted, normalized and confidence-scored fields.'
                : 'Correct a field to include a correction in a CORRECT decision.'
            }
          >
            <ReviewFields
              fields={reviewScreen.fields}
              corrections={corrections}
              onCorrectionsChange={setCorrections}
              readOnly={readOnly}
            />
          </Section>

          {/* 4. Signature & Stamp Verification */}
          <Section title="Signature & Stamp Verification">
            <ReviewDetections
              viewModel={viewModel}
              detections={reviewScreen.visual_detections}
            />
          </Section>

          {/* 5. Manual Review Checklist */}
          <Section
            title="Manual Review Checklist"
            note="Only actionable items are required to approve. NOT_VERIFIABLE items are skipped."
          >
            <ReviewChecklist
              requirements={checklistWithState}
              checked={checklist}
              onToggle={toggleChecklist}
              readOnly={readOnly}
              amcViewed={amcViewed}
              onAmcView={handleAmcView}
              amcViewUrl={amcViewUrl}
              amcDownloadUrl={amcDownloadUrl}
            />
          </Section>

          {/* 6. Decision */}
          {!readOnly ? (
            <Section title="Decision">
              <ReviewDecision
                reviewerName={reviewerName}
                decision={decision}
                onDecisionChange={setDecision}
                comments={comments}
                onCommentsChange={setComments}
                rejectionReason={rejectionReason}
                onRejectionReasonChange={setRejectionReason}
                checklist={checklistWithState}
                corrections={corrections}
                approvalBlocking={viewModel.approvalBlocking}
                requestableDocTypes={viewModel.requestableDocTypes}
                onRequestMissingDocs={handleRequestMissingDocs}
                submitting={submitting}
                readOnly={false}
                submitError={submitError}
                onSubmit={handleSubmit}
                condition={condition}
                onConditionChange={setCondition}
                dueDate={dueDate}
                onDueDateChange={setDueDate}
                additionalComments={additionalComments}
                onAdditionalCommentsChange={setAdditionalComments}
              />
            </Section>
          ) : (
            <Section title="Review History" note="Stored final review record for this application.">
              <ReviewHistory reviews={history} />
            </Section>
          )}

          {/* 7. Reviewer Comments — shared editable section, both pages use the same API */}
          <Section title="Reviewer Comments">
            <ReviewerComments
              applicationId={selectedId}
              defaultComment={
                viewModel?.summary?.actualFailures === 0
                  ? 'The submitted documents have been reviewed and validated. All required documentation has been received and verification checks have been completed successfully.'
                  : 'The submitted documents have been reviewed against the required documentation and verification criteria. Additional documents and/or clarification are required for the review to proceed. Please address the items identified in this report and provide the requested documents.'
              }
            />
          </Section>
        </>
      )}

      <ConfirmDialog
        open={pendingRejectPayload != null}
        title="Reject this application?"
        message={`Application #${selectedId} will be rejected. The rejection reason will be recorded permanently and the application cannot be approved afterwards.`}
        confirmLabel="Reject application"
        tone="danger"
        onConfirm={handleRejectConfirmed}
        onCancel={() => setPendingRejectPayload(null)}
      />
    </div>
  );
}

export default HumanReviewPage;
