/**
 * View model for the Human Review page.
 *
 * Wraps the review screen data from `useHumanReview` and derives semantic
 * state using the same shared utilities as the Validation Report. This
 * ensures both pages display identical counts for the same application.
 *
 * Additionally derives Human-Review-specific state: checklist requirements,
 * approval blocking issues, data-driven recommendations, and requestable
 * document types.
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
  getDocumentLabel,
} from '../utils/validationSemantic';

// ---------------------------------------------------------------------------
// Checklist derivation
// ---------------------------------------------------------------------------

/**
 * Maps checklist item names to the document type they require.
 * Items not in this map are "general" — always actionable regardless of
 * document state.
 */
const CHECKLIST_ITEM_DOCUMENT = {
  'Bank Maintenance Certificate originality confirmed': 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  'Authority Letter signature confirmed': 'AUTHORITY_LETTER',
  'Account Maintenance Certificate signature confirmed': 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  '1-Link Application signature confirmed': 'ONE_LINK_LETTER',
  'Tripartite Agreement signature confirmed': 'TRIPARTITE_AGREEMENT',
  'Business Requirement Document signature confirmed': 'BUSINESS_REQUIREMENT_DOCUMENT',
  'Formal Request Letter signature confirmed': 'FORMAL_REQUEST_LETTER',
  'Schedule of Charges / Bilateral signature confirmed': 'SCHEDULE_OF_CHARGES',
  'Account Maintenance Certificate stamp confirmed': 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  '1-Link Application stamp confirmed': 'ONE_LINK_LETTER',
  'Tripartite Agreement stamp confirmed': 'TRIPARTITE_AGREEMENT',
  'Schedule of Charges / Bilateral stamp confirmed': 'SCHEDULE_OF_CHARGES',
};

/**
 * Human-readable grouped labels for checklist items.
 */
const CHECKLIST_GROUP_LABELS = {
  authenticity: 'Document Authenticity',
  signatures: 'Signatures',
  stamps: 'Stamps',
  validation: 'Validation Findings',
};

/**
 * Human-readable display labels for checklist items that differ from the raw backend name.
 */
const CHECKLIST_DISPLAY_LABELS = {
  'Bank Maintenance Certificate originality confirmed': 'Account Maintenance Certificate Originality',
};

/**
 * Determine which checklist group an item belongs to.
 */
function getChecklistGroup(itemName) {
  if (itemName.includes('originality confirmed')) {
    return 'authenticity';
  }
  if (itemName.includes('signature confirmed')) {
    return 'signatures';
  }
  if (itemName.includes('stamp confirmed')) {
    return 'stamps';
  }
  return 'validation';
}

/**
 * Derive semantic status for each checklist item based on document availability.
 *
 * @param {object[]} backendChecklist Raw checklist items from the backend.
 * @param {Set<string>} missingDocTypes Set of missing document type strings.
 * @returns {Array<object>} Checklist items with semantic status.
 */
function deriveChecklistRequirements(backendChecklist, missingDocTypes) {
  return backendChecklist.map((item) => {
    const targetDoc = CHECKLIST_ITEM_DOCUMENT[item.item_name];
    const isGeneral = !targetDoc;
    const isAmcOriginality = item.item_name === 'Bank Maintenance Certificate originality confirmed';

    let semanticStatus;
    if (isGeneral) {
      // General items are always actionable
      semanticStatus = 'ACTIONABLE';
    } else if (missingDocTypes.has(targetDoc)) {
      semanticStatus = 'NOT_VERIFIABLE';
    } else {
      semanticStatus = 'ACTIONABLE';
    }

    const displayLabel = CHECKLIST_DISPLAY_LABELS[item.item_name] ?? item.item_name;

    return {
      ...item,
      itemName: item.item_name,
      label: displayLabel,
      semanticStatus,
      isGeneral,
      isAmcOriginality,
      targetDocument: targetDoc ?? null,
      group: getChecklistGroup(item.item_name),
      groupLabel: CHECKLIST_GROUP_LABELS[getChecklistGroup(item.item_name)],
    };
  });
}

/**
 * Group checklist items by their category.
 *
 * @param {object[]} requirements Derived checklist requirements.
 * @returns {Array<object>} Grouped checklist with per-group completion.
 */
function groupChecklist(requirements) {
  const groupMap = new Map();

  for (const item of requirements) {
    const groupKey = item.group;
    if (!groupMap.has(groupKey)) {
      groupMap.set(groupKey, {
        key: groupKey,
        label: item.groupLabel,
        items: [],
        actionableCount: 0,
        confirmedCount: 0,
      });
    }
    const group = groupMap.get(groupKey);
    group.items.push(item);
    if (item.semanticStatus === 'ACTIONABLE') {
      group.actionableCount += 1;
    }
    if (item.is_checked) {
      group.confirmedCount += 1;
    }
  }

  return [...groupMap.values()];
}

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------

/**
 * Build data-driven recommendations from the actual application state.
 * NOT sourced from report.recommendations (which may be stale or incorrect).
 *
 * @param {Set<string>} missingDocTypes Missing document types.
 * @param {object[]} genuineFailures Genuine validation failures.
 * @param {object[]} notVerifiableRules NOT_VERIFIABLE rules.
 * @param {object[]} pendingRules Pending rules.
 * @param {Array<object>} documents Grouped document list.
 * @returns {Array<object>} Recommendations with code and message.
 */
function buildRecommendations(missingDocTypes, genuineFailures, notVerifiableRules, pendingRules, documents) {
  const recommendations = [];

  // Missing documents
  for (const docType of missingDocTypes) {
    recommendations.push({
      code: `MISSING_${docType}`,
      message: `Missing required document: ${getDocumentLabel(docType)}`,
    });
  }

  // Duplicates (only excess copies — matches VR semantics)
  const duplicates = documents.filter((d) => d.status === 'duplicate');
  for (const dup of duplicates) {
    recommendations.push({
      code: `DUPLICATE_${dup.type}`,
      message: `Duplicate document: ${dup.label} — ${dup.copyCount} copies uploaded; expected ${dup.requiredCopies}`,
    });
  }

  // Genuine failures
  for (const rule of genuineFailures) {
    recommendations.push({
      code: `FAILURE_${rule.rule_id}`,
      message: `Review failed validation: ${rule.message}`,
    });
  }

  // NOT_VERIFIABLE — explain what's blocked
  for (const rule of notVerifiableRules) {
    recommendations.push({
      code: `NOT_VERIFIABLE_${rule.rule_id}`,
      message: rule.notVerifiableReason || `Cannot verify: ${rule.rule_name}`,
    });
  }

  // Pending checks — group by type
  const sigPending = pendingRules.filter((r) => r.rule_id?.startsWith('VIS_SIGNATURE_'));
  const stampPending = pendingRules.filter((r) => r.rule_id?.startsWith('VIS_STAMP_'));
  const otherPending = pendingRules.filter(
    (r) => !r.rule_id?.startsWith('VIS_SIGNATURE_') && !r.rule_id?.startsWith('VIS_STAMP_')
  );

  if (sigPending.length > 0) {
    recommendations.push({
      code: 'PENDING_SIGNATURES',
      message: `${sigPending.length} signature check${sigPending.length > 1 ? 's' : ''} pending`,
    });
  }
  if (stampPending.length > 0) {
    recommendations.push({
      code: 'PENDING_STAMPS',
      message: `${stampPending.length} stamp check${stampPending.length > 1 ? 's' : ''} pending`,
    });
  }
  if (otherPending.length > 0) {
    recommendations.push({
      code: 'PENDING_OTHER',
      message: `${otherPending.length} check${otherPending.length > 1 ? 's' : ''} pending`,
    });
  }

  return recommendations;
}

// ---------------------------------------------------------------------------
// Approval blocking
// ---------------------------------------------------------------------------

/**
 * Determine what blocks approval.
 *
 * Three independent blockers:
 * 1. Genuine validation failures
 * 2. Missing required documents
 * 3. Unchecked actionable checklist items
 *
 * NOT_VERIFIABLE checklist items do NOT block approval.
 *
 * @param {object} summary Summary counts.
 * @param {Set<string>} missingDocTypes Missing document types.
 * @param {object[]} checklistRequirements Derived checklist requirements.
 * @returns {{ blocked: boolean, failures: number, missingDocs: number, uncheckedActionable: number, reasons: string[] }}
 */
function deriveApprovalBlocking(summary, missingDocTypes, checklistRequirements) {
  const failures = summary.actualFailures;
  const missingDocs = missingDocTypes.size;
  const actionableItems = checklistRequirements.filter(
    (item) => item.semanticStatus === 'ACTIONABLE'
  );
  const uncheckedActionable = actionableItems.filter((item) => !item.is_checked).length;

  const reasons = [];
  if (failures > 0) {
    reasons.push(`${failures} validation failure${failures > 1 ? 's' : ''}`);
  }
  if (missingDocs > 0) {
    reasons.push(`${missingDocs} missing required document${missingDocs > 1 ? 's' : ''}`);
  }
  if (uncheckedActionable > 0) {
    reasons.push(
      `${uncheckedActionable} unchecked review item${uncheckedActionable > 1 ? 's' : ''}`
    );
  }

  return {
    blocked: failures > 0 || missingDocs > 0 || uncheckedActionable > 0,
    failures,
    missingDocs,
    uncheckedActionable,
    reasons,
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Derive the full Human Review view model.
 *
 * @param {object|null} reviewScreen The review screen payload from useHumanReview.
 * @returns {{ viewModel: object|null }} Derived semantic state.
 */
export function useHumanReviewViewModel(reviewScreen) {
  const viewModel = useMemo(() => {
    if (!reviewScreen) return null;

    const report = reviewScreen.report;
    const rules = report?.rules ?? [];
    const reportDocs = report?.document_summary ?? [];
    const completeness = report?.completeness;
    const normalized = reviewScreen.fields ?? [];

    // Classify failures (same logic as Validation Report)
    const failRules = rules.filter((r) => r.status === 'FAIL');
    const missingDocTypes = collectMissingDocTypes(completeness);

    const { genuine, notVerifiable } = classifyFailures(failRules, missingDocTypes);

    // Summary counts — identical to Validation Report
    const summary = deriveSummary(rules, genuine, notVerifiable);

    // Documents grouped by type (same as Validation Report)
    const documents = groupDocuments(reportDocs, completeness);

    // Fields summary
    const fields = deriveFields(normalized, report?.extraction_summary);

    // Visual verification (same as Validation Report)
    const visual = deriveVisual(report?.visual_detection_summary, missingDocTypes, rules);

    // Attention items (same as Validation Report)
    const missingDocTypesList = [...missingDocTypes];
    const duplicates = completeness?.duplicate_documents ?? [];
    const pendingRules = rules.filter((r) => r.status === 'PENDING_MANUAL_REVIEW');
    const attention = buildAttentionItems(genuine, missingDocTypesList, duplicates, pendingRules);

    // Rule groups (same as Validation Report)
    const ruleGroups = buildRuleGroups(rules, notVerifiable);

    // Human-Review-specific: checklist requirements
    const checklistRequirements = deriveChecklistRequirements(
      reviewScreen.checklist ?? [],
      missingDocTypes
    );
    const checklistGroups = groupChecklist(checklistRequirements);

    // Human-Review-specific: approval blocking
    const approvalBlocking = deriveApprovalBlocking(summary, missingDocTypes, checklistRequirements);

    // Human-Review-specific: recommendations (data-driven)
    const recommendations = buildRecommendations(
      missingDocTypes,
      genuine,
      notVerifiable,
      pendingRules,
      documents
    );

    // Human-Review-specific: requestable documents
    const requestableDocTypes = [...missingDocTypes];

    // Human-Review-specific: AMC presence check for originality workflow
    const amcPresent = !missingDocTypes.has('ACCOUNT_MAINTENANCE_CERTIFICATE');

    return {
      // Application info
      applicationId: reviewScreen.application_id,
      application: reviewScreen.application,

      // Shared with Validation Report (identical derivation)
      summary,
      fields,
      documents,
      visual,
      attention,
      ruleGroups,
      completeness,
      missingDocTypes,
      missingDocTypesList,

      // Human-Review-specific
      checklistRequirements,
      checklistGroups,
      approvalBlocking,
      recommendations,
      requestableDocTypes,
      amcPresent,
    };
  }, [reviewScreen]);

  return viewModel;
}
