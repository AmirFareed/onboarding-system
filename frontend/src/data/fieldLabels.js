/**
 * Human-readable labels for extracted document fields.
 *
 * Maps snake_case field keys (as produced by the extractors and stored in
 * extracted_fields / normalized_fields) to display-friendly labels. Used by
 * the redesigned validation report to avoid showing raw technical keys to
 * reviewers.
 */

export const FIELD_LABELS = {
  account_holder: 'Account Holder',
  account_number: 'Account Number',
  iban: 'IBAN',
  bank_name: 'Bank Name',
  branch_name: 'Branch Name',
  branch_code: 'Branch Code',
  statement_period: 'Statement Period',
  opening_balance: 'Opening Balance',
  closing_balance: 'Closing Balance',
  total_credits: 'Total Credits',
  total_debits: 'Total Debits',
  currency: 'Currency',
  transaction_count: 'Transaction Count',
  employee_name: 'Employee Name',
  employee_id: 'Employee ID',
  employer_name: 'Employer Name',
  gross_salary: 'Gross Salary',
  net_salary: 'Net Salary',
  salary_month: 'Salary Month',
  payment_date: 'Payment Date',
  full_name: 'Full Name',
  date_of_birth: 'Date of Birth',
  document_number: 'Document Number',
  nationality: 'Nationality',
  issue_date: 'Issue Date',
  expiry_date: 'Expiry Date',
  date_of_expiry: 'Date of Expiry',
  taxpayer_name: 'Taxpayer Name',
  tax_reference_number: 'Tax Reference Number',
  tax_year: 'Tax Year',
  gross_income: 'Gross Income',
  total_tax: 'Total Tax',
  organization_name: 'Organization Name',
  platform_name: 'Platform Name',
  transaction_charges: 'Transaction Charges',
  effective_date: 'Effective Date',
  subject: 'Subject',
  addressee: 'Addressee',
  date: 'Date',
  focal_person_name: 'Focal Person Name',
  focal_person_designation: 'Focal Person Designation',
  digitization_intent_confirmed: 'Digitization Intent Confirmed',
  revenue_services_listed: 'Revenue Services Listed',
  party_kpitb: 'Party KPITB',
  party_subbiller: 'Party Sub-Biller',
};

/**
 * Return a human-readable label for a field key.
 *
 * Falls back to a title-cased version of the raw key when no explicit
 * mapping exists.
 *
 * @param {string} key The snake_case field key.
 * @returns {string} A display-friendly label.
 */
export function getFieldLabel(key) {
  if (!key) return '';
  return (
    FIELD_LABELS[key] ??
    key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase())
  );
}
