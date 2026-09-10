/**
 * View model for the redesigned validation report.
 *
 * Wraps `useValidationReport` and derives semantic state using shared
 * utilities from `validationSemantic.js`. Components consume this hook's
 * output rather than understanding backend business logic.
 */
import { useMemo } from 'react';

import {
  collectMissingDocTypes,
  classifyFailures,
  groupDocuments,
  deriveFields,
  deriveVisual,
  buildAttentionItems,
  buildRuleGroups,
  deriveSummary,
} from '../utils/validationSemantic';
import { useValidationReport } from './useValidationReport';

/**
 * Derive the full validation report view model.
 *
 * Returns the raw useValidationReport data plus a `viewModel` object with
 * all derived semantic state. When no data is loaded, `viewModel` is null.
 */
export function useValidationReportViewModel() {
  const raw = useValidationReport();

  const viewModel = useMemo(() => {
    if (!raw.hasAnyData) return null;

    const rules = raw.rules ?? [];
    const reportDocs = raw.report?.document_summary ?? [];
    const completeness = raw.completeness;

    // Classify failures
    const failRules = rules.filter((r) => r.status === 'FAIL');
    const missingDocTypes = collectMissingDocTypes(completeness);

    const { genuine, notVerifiable } = classifyFailures(failRules, missingDocTypes);

    // Summary counts — single source of truth (shared with Human Review)
    const summary = deriveSummary(rules, genuine, notVerifiable);

    // Documents grouped by type
    const documents = groupDocuments(reportDocs, completeness);

    // Fields summary
    const fields = deriveFields(raw.normalized, raw.report?.extraction_summary);

    // Visual verification
    const visual = deriveVisual(raw.report?.visual_detection_summary, missingDocTypes, rules);

    // Attention items
    const missingDocTypesList = [...missingDocTypes];
    const duplicates = completeness?.duplicate_documents ?? [];
    const pendingRules = rules.filter((r) => r.status === 'PENDING_MANUAL_REVIEW');

    const attention = buildAttentionItems(genuine, missingDocTypesList, duplicates, pendingRules);

    // Rule groups with semantic statuses
    const ruleGroups = buildRuleGroups(rules, notVerifiable);

    return {
      application: raw.report?.application,
      overallStatus: raw.overallStatus,
      applicationStatus: raw.report?.application?.status ?? null,
      summary,
      fields,
      documents,
      visual,
      attention,
      ruleGroups,
      completeness,
      recommendations: raw.recommendations,
      sectionErrors: raw.sectionErrors,
    };
  }, [raw]);

  return useMemo(
    () => ({
      ...raw,
      viewModel,
    }),
    [raw, viewModel]
  );
}
