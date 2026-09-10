/**
 * Shared semantic derivation for validation data.
 *
 * Both the Validation Report and Human Review pages consume this module
 * to classify failures, derive visual counts, build attention items, and
 * group documents. Using a single source of truth prevents the two pages
 * from drifting apart in how they interpret the same backend data.
 */
import { getDocumentTypeConfig } from '../data/documents';

// ---------------------------------------------------------------------------
// Static mappings
// ---------------------------------------------------------------------------

/**
 * Maps DOC_*_PRESENT rule IDs to the document type they check.
 * Used to determine if a DOC_PRESENT failure is caused by a missing document
 * (NOT_VERIFIABLE) vs. excess copies (FAILED — genuine duplicate issue).
 */
export const DOC_RULE_TARGET_DOCUMENT = {
  DOC_TRIPARTITE_PRESENT: 'TRIPARTITE_AGREEMENT',
  DOC_BILATERAL_PRESENT: 'BILATERAL_AGREEMENT',
  DOC_AMC_PRESENT: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  DOC_ONE_LINK_PRESENT: 'ONE_LINK_LETTER',
  DOC_AUTHORITY_LETTER_PRESENT: 'AUTHORITY_LETTER',
  DOC_SCHEDULE_OF_CHARGES_PRESENT: 'SCHEDULE_OF_CHARGES',
  DOC_BRD_PRESENT: 'BUSINESS_REQUIREMENT_DOCUMENT',
  DOC_FORMAL_REQUEST_PRESENT: 'FORMAL_REQUEST_LETTER',
};

/**
 * Maps field-presence rule IDs to the document type they check.
 * Used to determine if a FLD_*_PRESENT failure is caused by a missing document
 * (NOT_VERIFIABLE) vs. a genuinely missing extracted field (FAILED).
 */
export const FIELD_TARGET_DOCUMENT = {
  FLD_IBAN_PRESENT: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  FLD_ACCOUNT_NUMBER_PRESENT: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  FLD_ACCOUNT_HOLDER_PRESENT: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  FLD_BANK_NAME_PRESENT: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  FLD_FORMAL_REQUEST_SUBJECT_PRESENT: 'FORMAL_REQUEST_LETTER',
  FLD_FORMAL_REQUEST_ORGANIZATION_PRESENT: 'FORMAL_REQUEST_LETTER',
  FLD_AUTHORITY_LETTER_ORGANIZATION_PRESENT: 'AUTHORITY_LETTER',
  FLD_AUTHORITY_LETTER_FOCAL_PERSON_PRESENT: 'AUTHORITY_LETTER',
  FLD_BRD_DIGITIZATION_INTENT_PRESENT: 'BUSINESS_REQUIREMENT_DOCUMENT',
  FLD_BILATERAL_PLATFORM_NAME_PRESENT: 'BILATERAL_AGREEMENT',
  FLD_BILATERAL_EFFECTIVE_DATE_PRESENT: 'BILATERAL_AGREEMENT',
};

/**
 * Maps visual rule IDs to the document type they check.
 * Sourced from backend/app/reports/constants.py VISUAL_TYPE_BY_RULE.
 */
export const VISUAL_TYPE_BY_RULE = {
  VIS_SIGNATURE_TRIPARTITE: 'TRIPARTITE_AGREEMENT',
  VIS_SIGNATURE_AMC: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  VIS_SIGNATURE_ONE_LINK: 'ONE_LINK_LETTER',
  VIS_SIGNATURE_AUTHORITY_LETTER: 'AUTHORITY_LETTER',
  VIS_SIGNATURE_BILATERAL: 'BILATERAL_AGREEMENT',
  VIS_SIGNATURE_FORMAL_REQUEST: 'FORMAL_REQUEST_LETTER',
  VIS_STAMP_TRIPARTITE: 'TRIPARTITE_AGREEMENT',
  VIS_STAMP_AMC: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
  VIS_STAMP_ONE_LINK: 'ONE_LINK_LETTER',
  VIS_STAMP_AUTHORITY_LETTER: 'AUTHORITY_LETTER',
  VIS_STAMP_BILATERAL: 'BILATERAL_AGREEMENT',
};

/**
 * Maps cross-document rule IDs to their participant document types.
 * Sourced from backend/app/rule_engine/rules/cross_document_rules.py.
 */
export const CROSS_PARTICIPANTS = {
  CROSS_IBAN_MATCH: ['ACCOUNT_MAINTENANCE_CERTIFICATE', 'BILATERAL_AGREEMENT'],
  CROSS_ACCOUNT_HOLDER_MATCH: ['ACCOUNT_MAINTENANCE_CERTIFICATE', 'TRIPARTITE_AGREEMENT'],
  CROSS_ACCOUNT_NUMBER_MATCH: [
    'ACCOUNT_MAINTENANCE_CERTIFICATE',
    'BILATERAL_AGREEMENT',
    'TRIPARTITE_AGREEMENT',
  ],
  CROSS_PERIOD_MATCH: ['ACCOUNT_MAINTENANCE_CERTIFICATE', 'BILATERAL_AGREEMENT'],
  CROSS_BRANCH_CODE_MATCH: ['ONE_LINK_LETTER', 'TRIPARTITE_AGREEMENT', 'AUTHORITY_LETTER'],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Return a human-readable label for a document type.
 *
 * @param {string} docType Backend document type enum value.
 * @returns {string} Display label.
 */
export function getDocumentLabel(docType) {
  return getDocumentTypeConfig(docType).label ?? docType;
}

/**
 * Extract the set of missing document types from the completeness report.
 *
 * @param {object|null} completeness Completeness report from the backend.
 * @returns {Set<string>} Set of missing document type strings.
 */
export function collectMissingDocTypes(completeness) {
  const missing = new Set();
  for (const req of completeness?.required_documents ?? []) {
    if (!req.is_present) {
      missing.add(req.document_type);
    }
  }
  for (const doc of completeness?.missing_documents ?? []) {
    missing.add(typeof doc === 'string' ? doc : doc.document_type);
  }
  return missing;
}

// ---------------------------------------------------------------------------
// Failure classification
// ---------------------------------------------------------------------------

/**
 * Classify FAIL rules as genuine failures or NOT_VERIFIABLE.
 *
 * Rules that fail because a required document is missing are downstream
 * consequences, not independent failures. The reviewer should see the root
 * cause (missing document) first.
 *
 * @param {object[]} failRules Rules with raw status FAIL.
 * @param {Set<string>} missingDocTypes Set of missing document type strings.
 * @returns {{ genuine: object[], notVerifiable: object[] }}
 */
export function classifyFailures(failRules, missingDocTypes) {
  const genuine = [];
  const notVerifiable = [];

  for (const rule of failRules) {
    const ruleId = rule.rule_id ?? '';
    let isDownstream = false;
    let reason = '';

    // DOC_*_PRESENT rules: check if the specific document is missing (NOT_VERIFIABLE)
    // or has excess copies (FAILED — genuine duplicate issue)
    if (ruleId.startsWith('DOC_') && ruleId.endsWith('_PRESENT')) {
      const targetDoc = DOC_RULE_TARGET_DOCUMENT[ruleId];
      if (targetDoc && missingDocTypes.has(targetDoc)) {
        notVerifiable.push({
          ...rule,
          notVerifiableReason: `${getDocumentLabel(targetDoc)} is missing`,
        });
      } else {
        genuine.push(rule);
      }
      continue;
    }

    // Visual rules: check if the target document is missing
    if (!isDownstream && (ruleId.startsWith('VIS_SIGNATURE_') || ruleId.startsWith('VIS_STAMP_'))) {
      const targetDoc = VISUAL_TYPE_BY_RULE[ruleId];
      if (targetDoc && missingDocTypes.has(targetDoc)) {
        isDownstream = true;
        reason = `${getDocumentLabel(targetDoc)} is missing`;
      }
    }

    // Cross-document rules: check if any participant document is missing
    if (!isDownstream && ruleId.startsWith('CROSS_')) {
      const participants = CROSS_PARTICIPANTS[ruleId];
      if (participants) {
        const missingParticipants = participants.filter((p) => missingDocTypes.has(p));
        if (missingParticipants.length > 0) {
          isDownstream = true;
          reason = `Required document${missingParticipants.length > 1 ? 's' : ''} missing: ${missingParticipants.map(getDocumentLabel).join(', ')}`;
        }
      } else if ((rule.related_document_ids ?? []).length === 0) {
        isDownstream = true;
        reason = 'Required documents are missing';
      }
    }

    // Field-presence rules: check if the target document is missing
    if (!isDownstream && ruleId.startsWith('FLD_') && ruleId.endsWith('_PRESENT')) {
      const targetDoc = FIELD_TARGET_DOCUMENT[ruleId];
      if (targetDoc && missingDocTypes.has(targetDoc)) {
        isDownstream = true;
        reason = `${getDocumentLabel(targetDoc)} is missing`;
      }
    }

    // Final fallback: if related_document_ids is empty and message indicates
    // a missing-document dependency, treat as not verifiable.
    // Skip FLD_*_PRESENT rules — they are already classified above based on
    // their specific target document.
    if (
      !isDownstream &&
      (rule.related_document_ids ?? []).length === 0 &&
      !(ruleId.startsWith('FLD_') && ruleId.endsWith('_PRESENT'))
    ) {
      const msg = (rule.message ?? '').toLowerCase();
      if (msg.includes('is missing') || msg.includes('cannot verify') || msg.includes('cannot compare')) {
        isDownstream = true;
        reason = 'Required document is missing. This check will become available when the required document is provided.';
      }
    }

    if (isDownstream) {
      notVerifiable.push({ ...rule, notVerifiableReason: reason });
    } else {
      genuine.push(rule);
    }
  }

  return { genuine, notVerifiable };
}

// ---------------------------------------------------------------------------
// Document grouping
// ---------------------------------------------------------------------------

/**
 * Group report documents by their required type, with copy details nested.
 *
 * Uses copy_count > requiredCopies for duplicate detection (matching the
 * Validation Report semantics). A document with exactly the required number
 * of copies is "present", not "duplicate".
 *
 * @param {object[]} reportDocs Document summary rows from the report.
 * @param {object|null} completeness Completeness report from the backend.
 * @returns {Array<object>} Grouped document list.
 */
export function groupDocuments(reportDocs, completeness) {
  const requiredDocs = completeness?.required_documents ?? [];
  const result = [];

  for (const req of requiredDocs) {
    const docs = (reportDocs ?? []).filter((d) => d.document_type === req.document_type);
    const config = getDocumentTypeConfig(req.document_type);

    let status = 'missing';
    if (req.is_present) {
      status = req.copy_count > config.requiredCopies ? 'duplicate' : 'present';
    }

    result.push({
      type: req.document_type,
      label: config.label,
      status,
      requiredCopies: config.requiredCopies,
      copyCount: req.copy_count,
      copies: docs.map((d) => ({
        documentId: d.document_id,
        processing: d.processing_status,
        quality: d.technical_validation_status,
        extraction: d.analysis_status,
      })),
    });
  }

  return result;
}

// ---------------------------------------------------------------------------
// Fields
// ---------------------------------------------------------------------------

/**
 * Derive the fields summary from the extraction summary.
 * One source of truth — no contradictory numbers.
 *
 * @param {object[]} normalized Normalized fields array.
 * @param {object|null} extractionSummary Extraction summary from the report.
 * @returns {{ total: number, verified: number, needsReview: number, progress: number }}
 */
export function deriveFields(normalized, extractionSummary) {
  const total = extractionSummary?.total_fields ?? normalized.length ?? 0;
  const verified = extractionSummary?.auto_verified ?? 0;
  const needsReview = extractionSummary?.pending_review ?? 0;
  const progress = total > 0 ? Math.round((verified / total) * 100) : 0;

  return { total, verified, needsReview, progress };
}

// ---------------------------------------------------------------------------
// Visual verification
// ---------------------------------------------------------------------------

/**
 * Derive visual verification counts including pending and not-verifiable.
 *
 * @param {object|null} visual Visual detection summary from the report.
 * @param {Set<string>} missingDocTypes Set of missing document type strings.
 * @param {object[]} rules Full rules array.
 * @returns {{ signatures: {present, missing, pending, notVerifiable}, stamps: {present, missing, pending, notVerifiable} }}
 */
export function deriveVisual(visual, missingDocTypes, rules) {
  if (!visual) {
    return {
      signatures: { present: 0, missing: 0, pending: 0, notVerifiable: 0 },
      stamps: { present: 0, missing: 0, pending: 0, notVerifiable: 0 },
    };
  }

  const visRules = (rules ?? []).filter(
    (r) => r.rule_id?.startsWith('VIS_SIGNATURE_') || r.rule_id?.startsWith('VIS_STAMP_')
  );

  let sigPending = 0;
  let sigNotVerifiable = 0;
  let stampPending = 0;
  let stampNotVerifiable = 0;

  for (const rule of visRules) {
    const isStamp = rule.rule_id.startsWith('VIS_STAMP_');

    if (rule.status === 'PENDING_MANUAL_REVIEW') {
      if (isStamp) stampPending++;
      else sigPending++;
    }

    if (rule.status === 'FAIL') {
      const targetDoc = VISUAL_TYPE_BY_RULE[rule.rule_id];
      if (targetDoc && missingDocTypes.has(targetDoc)) {
        if (isStamp) stampNotVerifiable++;
        else sigNotVerifiable++;
      }
    }
  }

  return {
    signatures: {
      present: visual.signature_detected ?? 0,
      missing: visual.signature_missing ?? 0,
      pending: sigPending,
      notVerifiable: sigNotVerifiable,
    },
    stamps: {
      present: visual.stamp_detected ?? 0,
      missing: visual.stamp_missing ?? 0,
      pending: stampPending,
      notVerifiable: stampNotVerifiable,
    },
  };
}

// ---------------------------------------------------------------------------
// Business rule groups
// ---------------------------------------------------------------------------

/**
 * Build rule groups with semantic statuses for each rule.
 *
 * @param {object[]} rules Full rules array.
 * @param {object[]} notVerifiableRules Rules classified as NOT_VERIFIABLE.
 * @returns {Array<object>} Rule groups with per-rule semantic status.
 */
export function buildRuleGroups(rules, notVerifiableRules) {
  const notVerifiableIds = new Set(notVerifiableRules.map((r) => r.rule_id));

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
        notVerifiable: 0,
        items: [],
      });
    }

    const group = byCategory.get(key);
    let semanticStatus;

    if (rule.status === 'PASS') {
      semanticStatus = 'PASSED';
      group.passed += 1;
    } else if (rule.status === 'WARNING') {
      semanticStatus = 'WARNING';
      group.warnings += 1;
    } else if (rule.status === 'PENDING_MANUAL_REVIEW') {
      semanticStatus = 'PENDING';
      group.pending += 1;
    } else if (rule.status === 'FAIL') {
      if (notVerifiableIds.has(rule.rule_id)) {
        semanticStatus = 'NOT_VERIFIABLE';
        group.notVerifiable += 1;
      } else {
        semanticStatus = 'FAILED';
        group.failed += 1;
      }
    } else {
      semanticStatus = 'PENDING';
      group.pending += 1;
    }

    const nvRule = notVerifiableRules.find((r) => r.rule_id === rule.rule_id);
    group.items.push({
      ...rule,
      semanticStatus,
      notVerifiableReason: nvRule?.notVerifiableReason ?? null,
    });
  }

  return [...byCategory.values()];
}

// ---------------------------------------------------------------------------
// Attention items
// ---------------------------------------------------------------------------

/**
 * Build the prioritized attention items for the "What Requires Attention" section.
 *
 * @param {object[]} genuineFailures Rules classified as genuine failures.
 * @param {Array<string|object>} missingDocs Missing document types.
 * @param {Array<object>} duplicates Duplicate document entries.
 * @param {object[]} pendingRules Rules with PENDING_MANUAL_REVIEW status.
 * @returns {Array<object>} Attention items grouped by type.
 */
export function buildAttentionItems(genuineFailures, missingDocs, duplicates, pendingRules) {
  const items = [];

  if (genuineFailures.length > 0) {
    items.push({
      type: 'failure',
      count: genuineFailures.length,
      label:
        genuineFailures.length === 1
          ? 'Actual Validation Failure'
          : 'Actual Validation Failures',
      details: genuineFailures.map((r) => ({
        title: r.rule_name,
        message: r.message,
      })),
    });
  }

  if (missingDocs.length > 0) {
    items.push({
      type: 'missingDoc',
      count: missingDocs.length,
      label:
        missingDocs.length === 1
          ? 'Required Document Missing'
          : 'Required Documents Missing',
      details: missingDocs.map((docType) => ({
        title: getDocumentLabel(docType),
        message: 'Required document was not uploaded',
      })),
    });
  }

  if (duplicates.length > 0) {
    items.push({
      type: 'duplicate',
      count: duplicates.length,
      label: duplicates.length === 1 ? 'Duplicate Document' : 'Duplicate Documents',
      details: duplicates.map((d) => {
        const docType = typeof d === 'string' ? d : d.document_type;
        const copyCount = typeof d === 'object' ? d.copy_count : null;
        const config = getDocumentTypeConfig(docType);
        return {
          title: getDocumentLabel(docType),
          message: copyCount
            ? `${copyCount} copies uploaded — expected ${config.requiredCopies}`
            : 'Duplicate copies detected',
        };
      }),
    });
  }

  if (pendingRules.length > 0) {
    const sigPending = pendingRules.filter(
      (r) => r.rule_id?.startsWith('VIS_SIGNATURE_')
    );
    const stampPending = pendingRules.filter(
      (r) => r.rule_id?.startsWith('VIS_STAMP_')
    );
    const otherPending = pendingRules.filter(
      (r) => !r.rule_id?.startsWith('VIS_SIGNATURE_') && !r.rule_id?.startsWith('VIS_STAMP_')
    );

    const details = [];
    if (sigPending.length > 0) {
      details.push({
        title: `${sigPending.length} signature check${sigPending.length > 1 ? 's' : ''}`,
        message: 'Awaiting automated visual verification',
      });
    }
    if (stampPending.length > 0) {
      details.push({
        title: `${stampPending.length} stamp check${stampPending.length > 1 ? 's' : ''}`,
        message: 'Awaiting automated visual verification',
      });
    }
    if (otherPending.length > 0) {
      details.push({
        title: `${otherPending.length} check${otherPending.length > 1 ? 's' : ''}`,
        message: 'Awaiting processing or manual review',
      });
    }

    items.push({
      type: 'pending',
      count: pendingRules.length,
      label: pendingRules.length === 1 ? 'Check Pending' : 'Checks Pending',
      details,
    });
  }

  return items;
}

// ---------------------------------------------------------------------------
// Summary derivation
// ---------------------------------------------------------------------------

/**
 * Derive the standard validation summary counts from rules and classified
 * failures. Both Validation Report and Human Review must use this function
 * to guarantee identical numbers for the same application.
 *
 * Invariant: totalChecks === passed + actualFailures + warnings + pending + notVerifiable
 *
 * @param {object[]} rules Full rules array.
 * @param {object[]} genuineFailures Rules classified as genuine failures.
 * @param {object[]} notVerifiableRules Rules classified as NOT_VERIFIABLE.
 * @returns {object} Summary counts.
 */
export function deriveSummary(rules, genuineFailures, notVerifiableRules) {
  return {
    totalChecks: rules.length,
    passed: rules.filter((r) => r.status === 'PASS').length,
    actualFailures: genuineFailures.length,
    warnings: rules.filter((r) => r.status === 'WARNING').length,
    pending: rules.filter((r) => r.status === 'PENDING_MANUAL_REVIEW').length,
    notVerifiable: notVerifiableRules.length,
  };
}
