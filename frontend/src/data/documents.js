/**
 * Document type catalogue.
 *
 * Mirrors the backend `DocumentType` enum (app/database/models/enums.py) so the
 * upload UI always sends a value the API accepts. Applications require a fixed
 * set of documents, some of them in multiple copies (a single 1-Link form is
 * uploaded three times, three Tripartite Agreement copies, etc.). The catalogue
 * below is the single source of truth for those requirements: the dashboard's
 * per-application checklist and the upload page's slot grid both derive their
 * required sets and copy counts from here.
 *
 * SCHEDULE_OF_CHARGES intentionally has no entry (removed 2026-08-22): it is
 * not a real standalone document in this checklist -- see CONTEXT.md.
 */

export const DOCUMENT_GROUP_REQUIRED = 'required';
export const DOCUMENT_GROUP_SUPPORTING = 'supporting';

export const DOCUMENT_TYPES = [
  {
    type: 'AUTHORITY_LETTER',
    label: 'Authority Letter',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 1,
  },
  {
    type: 'ACCOUNT_MAINTENANCE_CERTIFICATE',
    label: 'Account Maintenance Certificate',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 1,
  },
  {
    type: 'ONE_LINK_LETTER',
    label: '1-Link Application Form',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 3,
  },
  {
    type: 'TRIPARTITE_AGREEMENT',
    label: 'Tripartite Agreement',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 3,
  },
  {
    type: 'BUSINESS_REQUIREMENT_DOCUMENT',
    label: 'Onboarding / Business Requirement Document',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 1,
  },
  {
    type: 'BILATERAL_AGREEMENT',
    label: 'Bilateral / Business Agreement',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 1,
  },
  {
    type: 'CNIC',
    label: 'CNIC (Front & Back)',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 2,
    slotTypes: ['CNIC_FRONT', 'CNIC_BACK'],
    slotLabels: ['Front', 'Back'],
  },
  {
    type: 'FORMAL_REQUEST_LETTER',
    label: 'Formal Request Letter',
    group: DOCUMENT_GROUP_REQUIRED,
    requiredCopies: 1,
  },
  {
    type: 'OTHER_SUPPORTING_DOCUMENT',
    label: 'Other Supporting Document',
    group: DOCUMENT_GROUP_SUPPORTING,
    requiredCopies: 0,
  },
  {
    type: 'BULK_UPLOAD',
    label: 'Bulk Upload',
    group: DOCUMENT_GROUP_SUPPORTING,
    requiredCopies: 0,
  },
];

export const REQUIRED_DOCUMENT_TYPES = DOCUMENT_TYPES.filter(
  ({ group }) => group === DOCUMENT_GROUP_REQUIRED
);

export const SUPPORTING_DOCUMENT_TYPES = DOCUMENT_TYPES.filter(
  ({ group }) => group === DOCUMENT_GROUP_SUPPORTING
);

/**
 * Total number of required uploads per application
 * (1 + 1 + 3 + 3 + 1 + 1 + 2 + 1).
 */
export const TOTAL_REQUIRED_DOCUMENTS = REQUIRED_DOCUMENT_TYPES.reduce(
  (sum, entry) => sum + entry.requiredCopies,
  0
);

/**
 * Look up the catalogue entry for a document type value.
 *
 * Composite topics (e.g. CNIC front/back) map their backend slot types onto the
 * single catalogue entry so every view shows the same grouped topic.
 *
 * @param {string} type A backend `DocumentType` value.
 * @returns {object} The matching catalogue entry, or the fallback entry.
 */
export function getDocumentTypeConfig(type) {
  const bySlotType = DOCUMENT_TYPES.find(
    (entry) => entry.slotTypes && entry.slotTypes.includes(type)
  );
  return (
    bySlotType ??
    DOCUMENT_TYPES.find((entry) => entry.type === type) ??
    DOCUMENT_TYPES[0]
  );
}

/**
 * Compute upload progress from a list of uploaded documents.
 *
 * Shared by the dashboard checklist and the upload page so both views always
 * agree: a category is `complete` when it holds its required number of copies,
 * `incomplete` when at least one copy exists but the quota is unmet, and
 * `missing` when none of the required copies have been uploaded yet.
 *
 * @param {Array<object>} documents Uploaded document metadata.
 * @returns {{totalCopies: number, uploadedCopies: number, percent: number,
 *   categories: Array<object>}}
 */
export function computeDocumentProgress(documents = []) {
  const counts = {};
  for (const document of documents) {
    counts[document.document_type] = (counts[document.document_type] ?? 0) + 1;
  }

  const categories = REQUIRED_DOCUMENT_TYPES.map((entry) => {
    const present = entry.slotTypes
      ? entry.slotTypes.reduce((sum, slotType) => sum + (counts[slotType] ?? 0), 0)
      : counts[entry.type] ?? 0;
    let status = 'missing';
    if (present >= entry.requiredCopies) {
      status = 'complete';
    } else if (present > 0) {
      status = 'incomplete';
    }
    return {
      type: entry.type,
      label: entry.label,
      required: entry.requiredCopies,
      present,
      status,
    };
  });

  const uploadedCopies = categories.reduce((sum, category) => sum + category.present, 0);
  const totalCopies = TOTAL_REQUIRED_DOCUMENTS;
  const percent =
    totalCopies === 0 ? 0 : Math.round((Math.min(uploadedCopies, totalCopies) / totalCopies) * 100);

  return { totalCopies, uploadedCopies, percent, categories };
}

