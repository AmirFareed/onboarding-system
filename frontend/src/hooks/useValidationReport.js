import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { getAnalysisResults } from '../services/analysis';
import { listApplications } from '../services/applications';
import { getNormalizedFields } from '../services/normalization';
import { getValidationReport } from '../services/reports';
import { getTechnicalValidation } from '../services/technicalValidation';
import { getCompleteness, getValidationResults } from '../services/verification';
import { getApiErrorMessage } from '../utils/apiError';

const DEFAULT_STATUS = 'PENDING_REVIEW';

/**
 * Fetch one report section, normalising success and failure.
 *
 * Every section is fetched independently so a single 422 (the validation
 * report has no results yet) never hides the completeness or technical
 * validation data that does exist.
 */
async function fetchSection(request) {
  try {
    return { data: await request(), error: null };
  } catch (err) {
    return { data: null, error: getApiErrorMessage(err) };
  }
}

/**
 * Load everything the Validation Report page needs.
 *
 * Applications are listed through the shared list endpoint (optionally
 * filtered by status) so the operator can pick one. Selecting an application
 * triggers six read-only fetches in parallel: the aggregated validation
 * report, the completeness report, the technical validation reports, the
 * stored business-rule results, the document analysis results and the
 * normalized fields. Derived views (per-category rule totals, the issue list)
 * are computed client-side from the stored data.
 */
export function useValidationReport() {
  const [searchParams] = useSearchParams();
  const [applications, setApplications] = useState([]);
  const [appsLoading, setAppsLoading] = useState(true);
  const [appsError, setAppsError] = useState(null);
  const [statusFilter, setStatusFilter] = useState(DEFAULT_STATUS);
  const [selectedId, setSelectedId] = useState(() => {
    const fromQuery = searchParams.get('application');
    if (fromQuery != null && Number.isFinite(Number(fromQuery))) {
      return Number(fromQuery);
    }
    return null;
  });

  const [report, setReport] = useState(null);
  const [completeness, setCompleteness] = useState(null);
  const [technical, setTechnical] = useState(null);
  const [rules, setRules] = useState([]);
  const [analysis, setAnalysis] = useState({ items: [] });
  const [normalized, setNormalized] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sectionErrors, setSectionErrors] = useState({});
  const [error, setError] = useState(null);

  // Guards against out-of-order responses: switching the selected application
  // quickly enough (before an in-flight fetch for the previous one resolves)
  // must not let that stale response overwrite the newly-selected one.
  const reportRequestIdRef = useRef(0);

  // Same stale-response guard as useVerification.js's `reload` (activeAppId
  // ref, compared against a locally-captured value before every setState):
  // switching statusFilter quickly enough that two loadApplications calls
  // are in flight must not let the older one overwrite the newer one's
  // result.
  const activeStatusFilter = useRef(statusFilter);
  useEffect(() => {
    activeStatusFilter.current = statusFilter;
  }, [statusFilter]);

  const loadApplications = useCallback(async () => {
    const fetchStatusFilter = statusFilter;
    setAppsLoading(true);
    setAppsError(null);
    try {
      const { items } = await listApplications({
        status: fetchStatusFilter || undefined,
        limit: 100,
      });
      if (activeStatusFilter.current !== fetchStatusFilter) return;
      setApplications(items ?? []);
    } catch (err) {
      if (activeStatusFilter.current !== fetchStatusFilter) return;
      setAppsError(getApiErrorMessage(err));
      setApplications([]);
    } finally {
      if (activeStatusFilter.current === fetchStatusFilter) {
        setAppsLoading(false);
      }
    }
  }, [statusFilter]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadApplications();
  }, [loadApplications]);

  const reload = useCallback(async () => {
    const requestId = ++reportRequestIdRef.current;
    if (selectedId == null) {
      setReport(null);
      setCompleteness(null);
      setTechnical(null);
      setRules([]);
      setAnalysis({ items: [] });
      setNormalized([]);
      setSectionErrors({});
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    setSectionErrors({});
    const [
      reportSection,
      completenessSection,
      technicalSection,
      rulesSection,
      analysisSection,
      normalizedSection,
    ] = await Promise.all([
      fetchSection(() => getValidationReport(selectedId)),
      fetchSection(() => getCompleteness(selectedId)),
      fetchSection(() => getTechnicalValidation(selectedId)),
      fetchSection(() => getValidationResults(selectedId)),
      fetchSection(() => getAnalysisResults(selectedId)),
      fetchSection(() => getNormalizedFields(selectedId)),
    ]);
    if (requestId !== reportRequestIdRef.current) {
      return;
    }
    setReport(reportSection.data);
    setCompleteness(completenessSection.data);
    setTechnical(technicalSection.data);
    setRules(rulesSection.data?.results ?? []);
    setAnalysis(analysisSection.data ?? { items: [] });
    setNormalized(normalizedSection.data ?? []);
    setSectionErrors({
      report: reportSection.error,
      completeness: completenessSection.error,
      technical: technicalSection.error,
      rules: rulesSection.error,
      analysis: analysisSection.error,
      normalized: normalizedSection.error,
    });
    const hasOtherData =
      completenessSection.data != null ||
      (rulesSection.data?.results?.length ?? 0) > 0 ||
      (technicalSection.data?.items?.length ?? 0) > 0 ||
      (analysisSection.data?.items?.length ?? 0) > 0 ||
      (normalizedSection.data?.length ?? 0) > 0;
    if (reportSection.error && !hasOtherData) {
      setError(reportSection.error);
    }
    setLoading(false);
  }, [selectedId]);

  useEffect(() => {
    // Fetch-on-mount/selection-change via a memoized hook function -- see
    // AuthProvider.jsx or the full-stack audit (Phase 8) for why this
    // react-hooks/set-state-in-effect suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  const handleStatusChange = useCallback((value) => {
    setStatusFilter(value);
    setSelectedId(null);
  }, []);

  const handleSelect = useCallback((value) => {
    setSelectedId(value === '' ? null : Number(value));
  }, []);

  const handleRefresh = useCallback(() => {
    loadApplications();
    reload();
  }, [loadApplications, reload]);

  const hasAnyData =
    report != null ||
    rules.length > 0 ||
    (completeness?.uploaded_documents?.length ?? 0) > 0 ||
    (technical?.items?.length ?? 0) > 0 ||
    (analysis?.items?.length ?? 0) > 0 ||
    normalized.length > 0;

  const groupedRules = useMemo(() => {
    const byCategory = new Map();
    for (const rule of rules) {
      const key = rule.category_label ?? rule.rule_category ?? 'Other';
      if (!byCategory.has(key)) {
        byCategory.set(key, {
          label: key,
          passed: 0,
          failed: 0,
          warnings: 0,
          pending: 0,
          items: [],
        });
      }
      const group = byCategory.get(key);
      if (rule.status === 'PASS') {
        group.passed += 1;
      } else if (rule.status === 'FAIL') {
        group.failed += 1;
      } else if (rule.status === 'WARNING') {
        group.warnings += 1;
      } else {
        group.pending += 1;
      }
      group.items.push(rule);
    }
    return [...byCategory.values()];
  }, [rules]);

  const issues = useMemo(() => {
    const list = [];
    for (const rule of rules) {
      if (rule.status === 'PASS') {
        continue;
      }
      list.push({
        status: rule.status,
        severity: rule.severity,
        title: rule.rule_name,
        message: rule.message,
        category: rule.category_label ?? rule.rule_category,
      });
    }
    for (const doc of analysis?.items ?? []) {
      for (const issue of doc.issues ?? []) {
        list.push({ status: 'WARNING', title: doc.file_name, message: issue });
      }
    }
    return list;
  }, [rules, analysis]);

  return {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange: handleStatusChange,
    selectedId,
    onSelect: handleSelect,
    report,
    completeness,
    technical,
    rules,
    analysis,
    normalized,
    loading,
    error,
    sectionErrors,
    hasAnyData,
    overallStatus: report?.overall_status ?? null,
    groupedRules,
    issues,
    recommendations: report?.recommendations ?? [],
    onRefresh: handleRefresh,
  };
}