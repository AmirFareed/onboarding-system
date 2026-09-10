import { useCallback, useEffect, useMemo, useState, useRef } from 'react';

import { listDocuments } from '../services/documents';
import { getCompleteness, getValidationResults } from '../services/verification';
import { getApiErrorMessage } from '../utils/apiError';

const CATEGORY_ORDER = [
  'document_completeness',
  'field_presence',
  'format',
  'cross_document',
  'date',
  'visual',
  'policy',
  'quality',
];

const CATEGORY_LABELS = {
  document_completeness: 'Document completeness',
  field_presence: 'Required field presence',
  format: 'Field format',
  cross_document: 'Cross-document consistency',
  date: 'Date and period',
  visual: 'Visual verification',
  policy: 'Policy compliance',
  quality: 'Data quality',
};

/**
 * Derive the per-document verification status from its related rules.
 *
 * @param {object[]} rules Rules related to the document.
 * @returns {'VERIFIED'|'REVIEW_REQUIRED'|'FAILED'|'PENDING'}
 */
function deriveDocumentStatus(rules) {
  if (rules.some((rule) => rule.status === 'FAIL')) {
    return 'FAILED';
  }
  if (
    rules.some(
      (rule) => rule.status === 'WARNING' || rule.status === 'PENDING_MANUAL_REVIEW'
    )
  ) {
    return 'REVIEW_REQUIRED';
  }
  if (rules.length > 0) {
    return 'VERIFIED';
  }
  return 'PENDING';
}

/**
 * Map a stored severity to the issue-list grouping.
 *
 * @param {string} severity Backend severity value.
 * @returns {'CRITICAL'|'WARNING'|'REVIEW_REQUIRED'}
 */
function groupSeverity(severity) {
  if (severity === 'ERROR') {
    return 'CRITICAL';
  }
  if (severity === 'WARNING') {
    return 'WARNING';
  }
  return 'REVIEW_REQUIRED';
}

/**
 * Load everything the document verification workspace needs.
 *
 * Three read-only endpoints are fetched in parallel, each returning 200 even
 * when the application has no data: validation results (business rule
 * outcomes), the completeness report and the document list. Derived views are
 * computed client-side: overall status, summary cards, per-document status and
 * requirements, the cross-document panel and the severity-grouped issue list.
 * Internal rule ids and technical metadata are never surfaced.
 *
 * @param {number|string} applicationId Application id.
 */
export function useVerification(applicationId) {
  const [validationResults, setValidationResults] = useState([]);
  const [completeness, setCompleteness] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const activeAppId = useRef(applicationId);

  useEffect(() => {
    activeAppId.current = applicationId;
  }, [applicationId]);

  const reload = useCallback(async () => {
    const fetchAppId = applicationId;
    setLoading(true);
    setError(null);
    try {
      const [results, report, documentList] = await Promise.all([
        getValidationResults(fetchAppId),
        getCompleteness(fetchAppId),
        listDocuments(fetchAppId),
      ]);
      
      if (activeAppId.current !== fetchAppId) return;
      
      setValidationResults(results.results ?? []);
      setCompleteness(report);
      setDocuments(documentList.items ?? []);
    } catch (err) {
      if (activeAppId.current !== fetchAppId) return;
      setError(getApiErrorMessage(err));
    } finally {
      if (activeAppId.current === fetchAppId) {
        setLoading(false);
      }
    }
  }, [applicationId]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  const rules = validationResults;

  const overallStatus = useMemo(() => {
    if (rules.length === 0) {
      return 'PENDING';
    }
    if (rules.some((rule) => rule.status === 'FAIL')) {
      return 'FAILED';
    }
    if (
      rules.some(
        (rule) => rule.status === 'WARNING' || rule.status === 'PENDING_MANUAL_REVIEW'
      )
    ) {
      return 'REVIEW_REQUIRED';
    }
    return 'VERIFIED';
  }, [rules]);

  const summary = useMemo(() => {
    const requiredTotal = completeness?.required_documents?.length ?? 0;
    const requiredPresent = completeness?.required_documents?.filter(
      (item) => item.is_present
    ).length ?? 0;

    const visualRules = rules.filter((rule) => rule.rule_category === 'visual');
    const signatureRules = visualRules.filter((rule) =>
      /sign/i.test(`${rule.rule_name} ${rule.message ?? ''}`)
    );
    const stampRules = visualRules.filter((rule) =>
      /stamp/i.test(`${rule.rule_name} ${rule.message ?? ''}`)
    );
    const crossDocumentRules = rules.filter((rule) => rule.rule_category === 'cross_document');
    const fieldRules = rules.filter(
      (rule) =>
        rule.rule_category === 'field_presence' || rule.rule_category === 'format'
    );

    const countIssues = (items) => ({
      total: items.length,
      passed: items.filter((rule) => rule.status === 'PASS').length,
      failed: items.filter((rule) => rule.status === 'FAIL').length,
      warnings: items.filter(
        (rule) => rule.status === 'WARNING' || rule.status === 'PENDING_MANUAL_REVIEW'
      ).length,
    });

    return {
      completionPercentage: completeness?.completion_percentage ?? 0,
      requiredTotal,
      requiredPresent,
      signatures: countIssues(signatureRules),
      stamps: countIssues(stampRules),
      crossDocument: countIssues(crossDocumentRules),
      fields: countIssues(fieldRules),
    };
  }, [completeness, rules]);

  const documentsWithStatus = useMemo(
    () =>
      documents.map((document) => {
        const related = rules.filter((rule) =>
          (rule.related_document_ids ?? []).includes(document.id)
        );
        return {
          ...document,
          verification_status: deriveDocumentStatus(related),
          issue_count: related.filter((rule) => rule.status !== 'PASS').length,
          rules: related,
        };
      }),
    [documents, rules]
  );

  const missingDocuments = useMemo(() => {
    const presentTypes = new Set(
      (completeness?.required_documents ?? [])
        .filter((item) => item.is_present)
        .map((item) => item.document_type)
    );
    return (completeness?.required_documents ?? [])
      .filter((item) => !item.is_present)
      .map((item) => ({
        document_type: item.document_type,
        is_missing: !presentTypes.has(item.document_type),
      }));
  }, [completeness]);

  const issues = useMemo(() => {
    const grouped = { CRITICAL: [], WARNING: [], REVIEW_REQUIRED: [] };
    for (const rule of rules) {
      if (rule.status === 'PASS') {
        continue;
      }
      const group = rule.status === 'FAIL' ? 'CRITICAL' : groupSeverity(rule.severity);
      grouped[group].push({
        rule_name: rule.rule_name,
        message: rule.message,
        category_label: rule.category_label ?? CATEGORY_LABELS[rule.rule_category],
        status: rule.status,
        related_document_ids: rule.related_document_ids ?? [],
      });
    }
    return {
      critical: grouped.CRITICAL,
      warning: grouped.WARNING,
      reviewRequired: grouped.REVIEW_REQUIRED,
      total: grouped.CRITICAL.length + grouped.WARNING.length + grouped.REVIEW_REQUIRED.length,
    };
  }, [rules]);

  const crossDocumentRules = useMemo(
    () =>
      rules
        .filter((rule) => rule.rule_category === 'cross_document')
        .map((rule) => ({
          rule_name: rule.rule_name,
          message: rule.message,
          status: rule.status,
          related_document_ids: rule.related_document_ids ?? [],
        })),
    [rules]
  );

  const filteredDocuments = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return documentsWithStatus.filter((document) => {
      if (statusFilter && document.verification_status !== statusFilter) {
        return false;
      }
      if (!term) {
        return true;
      }
      return (
        String(document.id).includes(term) ||
        (document.document_type ?? '').toLowerCase().includes(term) ||
        (document.original_filename ?? '').toLowerCase().includes(term)
      );
    });
  }, [documentsWithStatus, searchTerm, statusFilter]);

  const handleSearchChange = useCallback((value) => {
    setSearchTerm(value);
  }, []);

  const handleStatusChange = useCallback((value) => {
    setStatusFilter(value);
  }, []);

  return {
    loading,
    error,
    reload,
    completeness,
    documents: filteredDocuments,
    documentsWithStatus,
    missingDocuments,
    overallStatus,
    summary,
    issues,
    crossDocumentRules,
    categoryOrder: CATEGORY_ORDER,
    categoryLabels: CATEGORY_LABELS,
    searchTerm,
    statusFilter,
    onSearchChange: handleSearchChange,
    onStatusChange: handleStatusChange,
  };
}
