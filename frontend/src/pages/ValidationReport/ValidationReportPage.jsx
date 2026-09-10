import { useState } from 'react';

import { Download, FileText, RefreshCw } from 'lucide-react';

import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import ReviewerComments from '../../components/common/ReviewerComments/ReviewerComments';
import { useToast } from '../../components/common/Toast/ToastContext';
import ReportActions from '../../components/report/ReportActions/ReportActions';
import ReportAttentionSection from '../../components/report/ReportAttentionSection/ReportAttentionSection';
import ReportCompleteness from '../../components/report/ReportCompleteness/ReportCompleteness';
import ReportFields from '../../components/report/ReportFields/ReportFields';
import ReportGroupedDocuments from '../../components/report/ReportGroupedDocuments/ReportGroupedDocuments';
import ReportRules from '../../components/report/ReportRules/ReportRules';
import ReportSummaryCards from '../../components/report/ReportSummaryCards/ReportSummaryCards';
import ReportTechnicalValidation from '../../components/report/ReportTechnicalValidation/ReportTechnicalValidation';
import ReportVisual from '../../components/report/ReportVisual/ReportVisual';
import { APPLICATION_STATUSES } from '../../data/statuses';
import { useValidationReportViewModel } from '../../hooks/useValidationReportViewModel';
import {
  downloadValidationReportPdf,
  getValidationReportHtmlUrl,
} from '../../services/reports';
import { formatDateTime } from '../../utils/format';
import styles from './ValidationReportPage.module.css';

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

function ReportSkeleton() {
  return (
    <div aria-hidden="true">
      <div className={styles.skeletonHeader} />
      <div className={styles.skeletonGrid}>
        {Array.from({ length: 5 }, (_, index) => (
          <div className={styles.skeletonCard} key={index} />
        ))}
      </div>
      <div className={styles.skeletonTable} />
    </div>
  );
}

/**
 * Redesigned operator-facing validation report.
 *
 * Uses the view model hook to derive semantic state: NOT_VERIFIABLE instead
 * of false failures, grouped documents, consistent summary counts, and
 * prioritized attention items. The reviewer sees root causes first, not
 * downstream consequences.
 */
function ValidationReportPage() {
  const toast = useToast();
  const {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange,
    selectedId,
    onSelect,
    report,
    technical,
    analysis,
    normalized,
    loading,
    error,
    sectionErrors,
    hasAnyData,
    onRefresh,
    viewModel,
  } = useValidationReportViewModel();

  const [pdfDownloading, setPdfDownloading] = useState(false);

  const printableUrl = selectedId != null ? getValidationReportHtmlUrl(selectedId) : null;

  const handleDownloadPdf = async () => {
    if (!selectedId) return;
    setPdfDownloading(true);
    try {
      await downloadValidationReportPdf(selectedId);
    } catch {
      toast.error('Failed to download PDF. Please try again.');
    } finally {
      setPdfDownloading(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Validation Report</h2>
        <p className={styles.subtitle}>
          Review the validation state, documents, checks, and extracted fields for an application.
        </p>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.filter} htmlFor="report-app-select">
          <span className={styles.filterLabel}>Application</span>
          <select
            id="report-app-select"
            className={styles.select}
            value={selectedId ?? ''}
            onChange={(event) => onSelect(event.target.value)}
            aria-label="Select an application to report on"
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

        <label className={styles.filter} htmlFor="report-status-filter">
          <span className={styles.filterLabel}>Status</span>
          <select
            id="report-status-filter"
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
          message="Choose an application above to load its validation report."
        />
      )}

      {selectedId != null && loading && <ReportSkeleton />}

      {selectedId != null && !loading && error && !hasAnyData && (
        <ErrorState message={error} onRetry={onRefresh} />
      )}

      {selectedId != null && !loading && !error && (
        <>
          {!hasAnyData && (
            <EmptyState
              title="No validation results yet"
              message="No validation data has been collected for this application yet."
              action={
                <button type="button" className={styles.primaryBtn} onClick={onRefresh}>
                  <RefreshCw aria-hidden="true" />
                  Refresh
                </button>
              }
            />
          )}

          {hasAnyData && viewModel && (
            <>
              {/* 1. Summary — overall status, counts, breakdown bar */}
              <Section title="Summary">
                <ReportSummaryCards viewModel={viewModel} />
              </Section>

              {sectionErrors.report && !report && (
                <p className={styles.reportUnavailable}>{sectionErrors.report}</p>
              )}

              {/* 2. What Requires Attention — failures, missing docs, duplicates, pending */}
              <Section title="What Requires Attention">
                <ReportAttentionSection attention={viewModel.attention} />
              </Section>

              {/* 3. Documents — grouped by type, copies nested */}
              <Section title="Documents">
                <ReportGroupedDocuments documents={viewModel.documents} />
              </Section>

              {/* 4. Completeness — progress bar + grouped list */}
              <Section title="Completeness">
                <ReportCompleteness completeness={viewModel.completeness} />
              </Section>

              {/* 5. Business Rules — category summaries, expandable */}
              <Section title="Business Rules">
                <ReportRules groups={viewModel.ruleGroups} />
              </Section>

              {/* 6. Extracted Fields — human-readable labels, grouped by doc */}
              <Section
                title="Extracted Fields"
                note="Extracted fields verified automatically from uploaded documents."
              >
                <ReportFields
                  normalized={normalized}
                  analysisItems={analysis.items}
                  fields={viewModel.fields}
                />
              </Section>

              {/* 7. Visual Verification — with pending/not-verifiable */}
              <Section title="Visual Verification">
                <ReportVisual visual={viewModel.visual} />
              </Section>

              {/* 8. Technical Details — collapsed by default */}
              {technical && technical.items && technical.items.length > 0 && (
                <Section title="Technical Details">
                  <details className={styles.details}>
                    <summary className={styles.detailsSummary}>
                      View technical validation results
                    </summary>
                    <ReportTechnicalValidation items={technical.items} />
                  </details>
                </Section>
              )}

              {/* 9. Review Actions */}
              <Section title="Review Actions">
                <ReportActions
                  applicationId={selectedId}
                  canApprove={viewModel.summary.actualFailures === 0}
                  canRequestDocuments={
                    (viewModel.completeness?.missing_documents?.length ?? 0) > 0
                  }
                  viewModel={viewModel}
                />
              </Section>

              {/* 10. Reviewer Comments — editable, shown before printable report */}
              <Section title="Reviewer Comments">
                <ReviewerComments
                  applicationId={selectedId}
                  defaultComment={
                    viewModel.summary.actualFailures === 0
                      ? 'The submitted documents have been reviewed and validated. All required documentation has been received and verification checks have been completed successfully.'
                      : 'The submitted documents have been reviewed against the required documentation and verification criteria. Additional documents and/or clarification are required for the review to proceed. Please address the items identified in this report and provide the requested documents.'
                  }
                />
              </Section>

              {/* 11. Printable Report */}
              {printableUrl && (
                <Section title="Printable Report">
                  <p className={styles.sectionNote}>
                    The report below is the final recipient-facing validation report.
                  </p>
                  <div className={styles.reportActions}>
                    <a
                      href={printableUrl}
                      target="_blank"
                      rel="noreferrer"
                      className={styles.primaryBtn}
                      aria-disabled={report == null}
                    >
                      <FileText aria-hidden="true" />
                      View / Print Report
                    </a>
                    <button
                      type="button"
                      className={styles.primaryBtn}
                      onClick={handleDownloadPdf}
                      disabled={report == null || pdfDownloading}
                    >
                      <Download aria-hidden="true" />
                      {pdfDownloading ? 'Generating PDF...' : 'Download PDF'}
                    </button>
                  </div>
                </Section>
              )}

              {report?.application && (
                <p className={styles.generatedAt}>
                  Report generated {formatDateTime(report.generated_at)} · version{' '}
                  {report.report_version}
                </p>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

export default ValidationReportPage;
