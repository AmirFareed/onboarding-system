"""Unit tests for the document analysis engine.

Covers document type detection, per-type field extraction, the reusable
validators, the cross-field consistency rules, the deterministic scoring and the
analysis repository. All fixtures are pure text, so no OCR engine or database
is needed except where explicitly noted.
"""

from pathlib import Path

import pytest

from app.database.connection import SessionLocal
from app.database.models.enums import ApplicationStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_analysis_repository import DocumentAnalysisRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.ocr_repository import OCRRepository
from app.document_analysis.constants import (
    AnalyzedDocumentType,
    VerificationStatus,
)
from app.document_analysis.exceptions import UnsupportedDocumentType
from app.document_analysis.extractors import (
    _parse_amount,
    detect_document_type,
    extract_fields,
)
from app.document_analysis.schemas import AnalysisOutcome
from app.document_analysis.services import DocumentAnalysisService
from app.document_processing.constants import PAGE_SEPARATOR
from app.document_analysis.rules import (
    RulesEngine,
    compute_score,
    compute_verification_status,
    scoring_components,
)
from app.document_analysis.validators import (
    ValidatorEngine,
    validate_account_number,
    validate_currency,
    validate_date,
    validate_date_not_future,
    validate_iban,
    validate_salary_month,
)

BANK_STATEMENT_TEXT = """MONTHLY ACCOUNT STATEMENT
Account Holder: John A. Doe
Account Number: 1234567890
IBAN: DE89370400440532013000
Bank: Sparkasse
Statement Period: 01/01/2026 - 31/01/2026
Opening Balance: 1,250.50
Closing Balance: 3,200.75
Total Credits: 2,500.00
Total Debits: 549.75
Currency: EUR
Transactions: 23
"""

PAYSLIP_TEXT = """PAYSLIP
Employee Name: Jane Q. Roe
Employee ID: EMP-1001
Employer Name: Acme Corp GmbH
Gross Salary: 5,000.00
Net Salary: 3,850.50
Salary Month: 2026-01
Payment Date: 2026-01-31
"""

ID_TEXT = """NATIONAL IDENTITY CARD
Full Name: Jose P. Garcia
Date of Birth: 1990-05-15
ID Number: 1234567890
Nationality: Spain
Issue Date: 2018-06-01
Expiry Date: 2028-06-01
"""

TAX_TEXT = """TAX RETURN SUMMARY
Taxpayer Name: Maria K. Novak
Tax Reference Number: TAX-2025-000123
Tax Year: 2025
Gross Income: 45,000.00
Total Tax: 9,800.00
Currency: EUR
"""

#: Synthetic (fabricated, non-real) fixture mirroring the structural pattern
#: docs/Master_Rules_Combined.md Section 7 describes for a Bilateral
#: Agreement -- department name, PayMin/Digital Muhasil/Paymere BCX platform
#: terminology, a Section 5.2 PKR transaction-charge line and a Section 6
#: account block. Never real extracted values.
#: Fabricated data (PK98FAKE IBAN -- checksum-valid so FormatIbanRule accepts
#: it, unlike the other fixtures' PK99FAKE placeholders below -- "Sample"
#: department), real template wording
#: -- mirrors the real "AGREEMENT FOR DIGITAL PAYMENT COLLECTION VIA PAYMIR"
#: structure confirmed 2026-08-22 against two independent real departments
#: (Conservator Wildlife Peshawar Zoo, a second KP department). The original
#: version of this fixture (labeled "Department:"/"Section 5.2:"/"Account
#: Title:"/"Effective Date:" fields, "PayMin" platform) matched none of the
#: two real samples at all -- replaced, not just re-asserted. Effective date
#: filled ("this 09 day of 03, 2026") -- see the _UNFILLED variant below for
#: the other real, confirmed template shape (blank date).
BILATERAL_AGREEMENT_TEXT = """AGREEMENT
FOR DIGITAL PAYMENT COLLECTION VIA PAYMIR
BETWEEN
Khyber Pakhtunkhwa Information Technology Board
AND
Sample Regional Development Authority

This Agreement is made and entered into on this 09 day of 03, 2026, at Peshawar,
By and Between:
Khyber Pakhtunkhwa Information Technology Board (KPITB), hereinafter referred as First party
or Party A or Party 1;
and
Sample Regional Development Authority, Government of Khyber Pakhtunkhwa, Peshawar,
having its registered office at Sample Road, Peshawar, hereinafter referred to as "Client" or
Second Party or Party B or Party 2 which expression shall, unless repugnant to the context,
include its successors-in-interests.

"PAYMIR" means Digital Payment Gateway developed by the KPITB.

5. PAYMENT METHODS & CHARGES
5.1.The following payment methods shall be available to citizens through Paymir:
5.2.Transaction Charges:
Amount in PKR (Transaction Range)
Transaction Charges (Including 1-LINK)
PKR 1-10,000
PKR 25.00 per transaction
6. DEPOSIT & DISBURSEMENT OF FUNDS
6.1.All payments collected through Paymir shall be deposited directly into the provided Bank of
the Sample Regional Development Authority as follow:
Sr No
Bank Name
Account No
01
Bank of Fake Branch
PK98FAKE00012345678901
"""

#: Same real template, unfilled effective-date clause -- confirmed real
#: (one of the two real samples leaves this blank: "on this day of , 20__").
#: Everything else identical to BILATERAL_AGREEMENT_TEXT.
BILATERAL_AGREEMENT_TEXT_UNFILLED_DATE = BILATERAL_AGREEMENT_TEXT.replace(
    "on this 09 day of 03, 2026, at Peshawar,",
    "on this day of , 20__, at Peshawar,",
)

#: Synthetic (fabricated, non-real), mirroring a real structural pattern found
#: 2026-08-26 on both real Bilateral samples (Confidential Data/.ocr_cache/
#: Conservator_Wildlife_Peshawar_Zoo and schdule_of_charges_or_bilateral) and
#: confirmed live on application 20322 document 42978: a second e-stamp/
#: STAMPING cover page is physically bound mid-Section-5, between the fee
#: table and Section 6 -- a real, expected artifact of Pakistani stamp-paper
#: documents, not scan noise. Before this date, BilateralAgreementExtractor's
#: transaction_charges pattern only recognized this boundary via the OCR
#: cache tool's own "--- page break ---" marker (backend/scripts/ocr_cache.py
#: -- never written by production code), so it worked against both cached
#: fixtures but silently captured the whole intervening stamp page as noise
#: against real application.raw_ocr_text, which is joined with
#: app.document_processing.constants.PAGE_SEPARATOR instead. This fixture
#: uses that real production separator, not the cache tool's marker, so it
#: actually exercises what a live pipeline run produces.
BILATERAL_AGREEMENT_TEXT_WITH_INTERVENING_STAMP_PAGE = (
    BILATERAL_AGREEMENT_TEXT.replace(
        "PKR 25.00 per transaction\n6. DEPOSIT & DISBURSEMENT OF FUNDS",
        "PKR 25.00 per transaction\nCS\nCamScanner"
        + PAGE_SEPARATOR.format(page_index=5)
        + "STAMPING\nVND042026SAMPLE\nKP-PSW-SAMPLE\nNon-Judicial\nRs.150\n"
        "Description\n: AGREEMENT\nFirst Party\n: KP IT Board [-]\n"
        "Second Party\n: , Sample Authority [-]\nVendor Information\n"
        ": Sample Vendor [00000-0000000-0]\nIssued Date\n"
        ": 05-April-2026 22:07:PM\nAmount in words\n"
        ": One Hundred Fifty Rupees Only\nStamp paper Expiry Date\n"
        ": 03-August-2026\nThe transaction charges will be over and above "
        "to the fee and will be collected by the citizen at source.\n"
        "6. DEPOSIT & DISBURSEMENT OF FUNDS",
    )
)

#: Synthetic (fabricated, non-real) fixtures mirroring the real prose-embedded
#: Authority Letter template confirmed on two independent real departments in
#: Confidential Data/ -- structurally near-identical wording, one using a
#: comma before the designation, the other parenthesizing it. Never real
#: extracted values.
#: A letterhead line precedes the title, matching the real DG Sports shape
#: this fixture's "on the behalf of Directorate." sentence was modeled on --
#: added 2026-08-26 once real evidence confirmed bare "Directorate" is a
#: generic self-reference, not a complete organization name (see
#: AuthorityLetterExtractor's class docstring); without a letterhead to fall
#: back to, this previously asserted the *old, now-known-incomplete* value.
AUTHORITY_LETTER_TEXT_COMMA_FORM = """SAMPLE DIRECTORATE GENERAL
AUTHORITY LETTER
It is hereby authorized that Mr. Naveed Khan, Deputy Director Administration \
(BPS-18) is authorized to deal with and conduct correspondence and matter \
related to 1-Link and the Khyber Pakhtunkhwa Information Technology Board \
(KPITB) on the behalf of Directorate.
"""

AUTHORITY_LETTER_TEXT_PAREN_FORM = """AUTHORITY LETTER
It is hereby authorized that Mr. Salman Raza (Assistant Finance Officer) \
Tehsil Municipal Administration Sample is authorized to deal with and \
conduct correspondence and matters related to 1-Link and the Khyber \
Pakhtunkhwa Information Technology Board (KPITB) on behalf of TMA Sample \
District.
"""

#: The issue-date label sits in the letterhead, before the certifying
#: sentence -- moved there 2026-08-26 to match the real corpus (Confidential
#: Data/.ocr_cache/, 7 samples across 4 banks): every real sample states its
#: own issue date in the header, never inside the post-certification detail
#: block alongside Account Number/IBAN/Bank Name/Branch Name as this fixture
#: previously placed it -- that placement was never confirmed against a real
#: sample and, once checked, doesn't match how any real AMC is laid out (see
#: AccountMaintenanceCertificateExtractor's class docstring and CONTEXT.md).
ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT = """FUTURE BANK LIMITED
ACCOUNT MAINTENANCE CERTIFICATE
Date of Issue: 15/08/2026

This is to certify that the following account is maintained with us:

Account Title: KHYBER PROVINCE UTILITIES BOARD
Account Number: 01234567890123
IBAN: PK36FUTB0000001123456702
Bank Name: Future Bank Limited
Branch Name: Main Branch, Peshawar
"""

#: party_subbiller's clause below ("<org> hereby irrevocably undertakes...")
#: mirrors the real confirmed template shape, not the "(hereinafter referred
#: to as the 'Sub-biller')" convention this fixture used before 2026-08-26 --
#: that convention was never confirmed present in any real sample and, once
#: checked against the one real Tripartite sample on file, turned out to be
#: wrong: the real document leaves that exact clause's placeholder unfilled
#: ("(Sub Biller Name)") and states the sub-biller only in prose elsewhere.
#: See CONTEXT.md and TripartiteAgreementExtractor's class docstring for the
#: full real-sample evidence (11 other real cached files, 8+ independent
#: organizations, all sharing this same "hereby irrevocably undertakes"
#: clause from the same underlying 1LINK template).
TRIPARTITE_AGREEMENT_TEXT = """TRIPARTITE AGREEMENT
This Tripartite Agreement is made and entered into by and between:
1-Link (Private) Limited, having its registered office at 4th Floor, State Life Building, Karachi (hereinafter referred to as '1-Link')
Khyber Pakhtunkhwa Information Technology Board, having its registered office at Civil Secretariat, Peshawar (hereinafter referred to as 'KPITB')
Transport and Mass Transit Department hereby irrevocably undertakes, agrees and acknowledges that it shall be bound by the Agreement.

Bank Details:
Account Title: KHYBER PROVINCE UTILITIES BOARD
Account Number: 01234567890123
Branch: Main Branch, Peshawar
"""

#: Synthetic (fabricated, non-real) fixtures mirroring the three real BRD
#: structural variants confirmed in Confidential Data/ (three independent
#: departments) -- unlike Authority Letter, no shared template exists, so
#: each fixture mirrors a different real department's actual shape rather
#: than one clean case. Never real extracted values.
BRD_TEXT_PROSE_FORM = """BUSINESS REQUIREMENT DOCUMENT
The Directorate of Sample Affairs, Sample Province, was established in 1995
and provides recreational facilities across the region. Visitors register
for membership and pay the prescribed fees at each facility office.
For ease and transparency, this office is already collaborating with KPITB
on a Management Information System and plans to integrate digital payment
solutions through KPITB's FinTech Unit within the system.
"""

BRD_TEXT_NUMBERED_LIST_FORM = """BUSINESS REQUIREMENT DOCUMENTS
Tehsil Municipal Administration Sample is a local government entity
responsible for providing Municipal Services to the general public. The
major sources of Income of this TMA are:
1. General Bus Stand
2. Cattle Fair Sample
3. Service Fee
INTENTION TO ON-BOARD DEPARTMENT FOR THE ENABLEMENT OF THE DIGITAL
PAYMENTS VIA KPITB's FIN TECH UNIT
This Office intends to go towards Digital Payments via KPITB'S FIN TECH
UNIT.
"""

BRD_TEXT_CATEGORIZED_BULLETS_FORM = """Business Requirement Document
1. Brief Background of Department:
The Sample Development Authority is a government organization responsible
for planning and development in the Sample region.
2. SERVICES OFFERED:
Revenue Collection
Taxes (Property Tax, Water Tax)
Miscellaneous (Registration Fee, Lease Renewal, Rents)
4. Intention to on-board department for the enablement of the digital
payments via KPITB's FinTech Unit
The Authority intends to collaborate with KPITB's FinTech Unit to digitize
all revenue streams.
"""

#: Missing the digitization-intent confirmation entirely -- a real BRD would
#: never omit this per docs/Master_Rules_Combined.md Section 10, but the
#: extractor must still degrade honestly (missing, not invalid) rather than
#: raise.
BRD_TEXT_NO_DIGITIZATION_MENTION = """BUSINESS REQUIREMENT DOCUMENT
The Directorate of Sample Affairs was established in 1995 and provides
recreational facilities across the region. Visitors pay the prescribed
fees at each facility office.
"""

#: Missing the services-list mention -- unlike the digitization-intent case
#: above, this field is non-critical, but Section 10 still requires it, so
#: its absence must stay visible to a human reviewer (a "missing" validation
#: result and a downgraded, non-VERIFIED status) rather than being hidden by
#: the non-critical classification.
BRD_TEXT_NO_SERVICES_MENTION = """BUSINESS REQUIREMENT DOCUMENT
The Directorate of Sample Affairs, Sample Province, was established in 1995
and provides recreational facilities across the region.
For ease and transparency, this office is already collaborating with KPITB
on a Management Information System and plans to integrate digital payment
solutions through KPITB's FinTech Unit within the system.
"""


#: Synthetic (fabricated, non-real) fixture mirroring the real single-account
#: clause-(v)/clause-(x) shape found in one of the two real organizations
#: (Confidential Data/.ocr_cache/TMA_Khal_Dir_Lower__ONE_LINK_LETTER_copy1.txt):
#: one specific account stated in one sentence, with an unambiguous branch code
#: in a nested parenthetical. Never real extracted values.
ONE_LINK_LETTER_TEXT_SINGLE_ACCOUNT = """PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS
(v)
hereby authorize 1LINK for each transaction to carry out settlement and clearing functions as per
Operating Guidelines, in the bank account number (IBAN) PK00SAMP0000000000000000 titled as Sample General Account
SAMPLE TEHSIL MUNICIPAL ADMINISTRATION maintained with (SAMPLE BANK) in its
branch (Sample Road Branch (0099)):
(x)
shall ensure business continuity planning (BCP) and disaster recovery (DR) at their side. SAMPLE
TEHSIL MUNICIPAL ADMINISTRATION hereby authorizes 1LINK to take actions, as it deems
necessary, to ensure BCP, DR, business operations and network connectivity and SAMPLE
TEHSIL MUNICIPAL ADMINISTRATION will accept such measures.
"""

#: Synthetic (fabricated, non-real) fixture mirroring the real multi-bank
#: reference-table shape found in the other real organization (Confidential
#: Data/.ocr_cache/GDA_Abbotabad__ONE_LINK_LETTER_copy1-3.txt): organization
#: name is still present via clause (x), but clause (v)'s bank details are a
#: table of several banks with no textual indication of which is operative --
#: branch_code must come back missing here, not a guessed row. Never real
#: extracted values.
ONE_LINK_LETTER_TEXT_MULTI_BANK_TABLE = """PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS
(x)
shall ensure business continuity planning (BCP) and disaster recovery (DR) at their side. SAMPLE
DEVELOPMENT AUTHORITY hereby authorizes 1LINK to take actions, as it deems
necessary, to ensure BCP, DR, business operations and network connectivity and SAMPLE
DEVELOPMENT AUTHORITY accept such measures.
(v)
Agreement or as communicated through 1LINK Schedule of Charges from time to time, in the
FOLLOWING bank accounts:
Sr No. Bank Name Account No
1. Sample Bank One
Sample Branch
PK00 SAMP 0000 0000 0000 0000
2. Sample Bank Two
Sample Road Branch (0099)
PK00 SAMB 0000 0000 0000 0001
"""

#: Missing the organization-name clause entirely -- organization_name is
#: critical for this type, so its absence must force manual review rather
#: than a silent pass.
ONE_LINK_LETTER_TEXT_NO_ORG_NAME = """PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS
(v)
hereby authorize 1LINK for each transaction to carry out settlement and clearing functions.
(vi)
for each Transaction carried out by the Sub-Billers/Bill Aggregator Member, shall abide by the
Operating Guidelines.
"""


#: Synthetic (fabricated, non-real), mirroring the clean label-then-value
#: layout confirmed in 2 of 3 real cached samples (Confidential Data/.ocr_cache/,
#: DG_Sports_KP_Onboarding_Documents__CNIC_FRONT_copy1/2.txt): each label sits
#: on its own line, immediately followed by its value -- single labels get a
#: single value line, adjacent label pairs get a matching value-pair.
CNIC_FRONT_TEXT_CLEAN = """PAKISTAN
National Identity Card
ISLAMIC REPUBLIC OF PAKISTAN
Name
Samia Naz
Father Name
Nasir Mehmood
Gender
Country of Stay
F
Pakistan
Identity Number
Date of Birth
12345-1234567-1
01.01.1990
Date of Issue
Date of Expiry
01.01.2020
01.01.2030
Holder's Signature
12345-1234567-1
Registrar General of Pakistan
"""

#: Synthetic (fabricated, non-real), mirroring the scrambled read-order
#: confirmed in the third real cached sample (copy3.txt): labels and values
#: are interleaved out of order except for the "Name" label, which -- by the
#: same coincidence seen in the real sample -- still sits directly before its
#: value. document_number and full_name must still extract; date_of_expiry's
#: two-label/two-value block never occurs intact, so it must honestly miss.
CNIC_FRONT_TEXT_SCRAMBLED = """76494
ISLAMIC REPUBLIC OF PAKISTAN
PAKISTAN
Date of Issue
Identity Number
GenderCountry of Stay
01.01.2020
12345-1234567-1
Father Name
F
Name
Samia Naz
Nasir Mehmood
Pakistan
Date of Expiry
Date of Birth
National Identity Card
01.01.1990
Holder's Signature
"""

#: Missing only the "Name" clause -- document_number and date_of_expiry both
#: still extract, so this isolates full_name's absence from the other two
#: expected fields (unlike a text missing everything, which would drag the
#: score down for unrelated reasons and force review regardless of full_name).
CNIC_FRONT_TEXT_NO_NAME = """PAKISTAN
National Identity Card
ISLAMIC REPUBLIC OF PAKISTAN
Identity Number
Date of Birth
12345-1234567-1
01.01.1990
Date of Issue
Date of Expiry
01.01.2020
01.01.2030
Holder's Signature
"""


def _components(text: str):
    document_type = detect_document_type(text)
    fields = extract_fields(text, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    consistency = RulesEngine().run(document_type, fields)
    return document_type, fields, validations, consistency


# --- Document type detection -------------------------------------------------


def test_detect_bank_statement():
    assert detect_document_type(BANK_STATEMENT_TEXT) is AnalyzedDocumentType.BANK_STATEMENT


def test_detect_payslip():
    assert detect_document_type(PAYSLIP_TEXT) is AnalyzedDocumentType.PAYSLIP


def test_detect_identity_document():
    assert detect_document_type(ID_TEXT) is AnalyzedDocumentType.ID_DOCUMENT


def test_detect_tax_document():
    assert detect_document_type(TAX_TEXT) is AnalyzedDocumentType.TAX_DOCUMENT


def test_detect_unknown_document():
    text = "This is a casual letter with no financial keywords whatsoever."
    assert detect_document_type(text) is AnalyzedDocumentType.UNKNOWN


def test_detection_is_case_insensitive():
    assert detect_document_type(BANK_STATEMENT_TEXT.lower()) is AnalyzedDocumentType.BANK_STATEMENT


# --- Field extraction --------------------------------------------------------


def test_extract_bank_statement_fields():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    assert fields["account_holder"] == "John A. Doe"
    assert fields["account_number"] == "1234567890"
    assert fields["iban"] == "DE89370400440532013000"
    assert fields["bank_name"] == "Sparkasse"
    assert fields["statement_period"] == {"start": "2026-01-01", "end": "2026-01-31"}
    assert fields["opening_balance"] == 1250.5
    assert fields["closing_balance"] == 3200.75
    assert fields["total_credits"] == 2500.0
    assert fields["total_debits"] == 549.75
    assert fields["currency"] == "EUR"
    assert fields["transaction_count"] == 23


def test_extract_payslip_fields():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    assert fields["employee_name"] == "Jane Q. Roe"
    assert fields["employee_id"] == "EMP-1001"
    assert fields["employer_name"] == "Acme Corp GmbH"
    assert fields["gross_salary"] == 5000.0
    assert fields["net_salary"] == 3850.5
    assert fields["salary_month"] == "2026-01"
    assert fields["payment_date"] == "2026-01-31"


def test_extract_identity_fields():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    assert fields["full_name"] == "Jose P. Garcia"
    assert fields["date_of_birth"] == "1990-05-15"
    assert fields["document_number"] == "1234567890"
    assert fields["nationality"] == "Spain"
    assert fields["issue_date"] == "2018-06-01"
    assert fields["expiry_date"] == "2028-06-01"


def test_extract_tax_fields():
    fields = extract_fields(TAX_TEXT, AnalyzedDocumentType.TAX_DOCUMENT)
    assert fields["taxpayer_name"] == "Maria K. Novak"
    assert fields["tax_reference_number"] == "TAX-2025-000123"
    assert fields["tax_year"] == 2025
    assert fields["gross_income"] == 45000.0
    assert fields["total_tax"] == 9800.0
    assert fields["currency"] == "EUR"


def test_extract_unknown_type_raises():
    with pytest.raises(UnsupportedDocumentType):
        extract_fields("some text", AnalyzedDocumentType.UNKNOWN)


def test_extract_bilateral_agreement_fields():
    """Real-sample-validated 2026-08-22 (Conservator Wildlife Peshawar Zoo +
    a second independent department) -- see BilateralAgreementExtractor's
    docstring for the full rewrite rationale. account_holder is a deliberate
    honest miss, not asserted here: neither real sample's bank-account table
    has an Account Title/Holder column, only Bank Name + Account No.
    """
    fields = extract_fields(
        BILATERAL_AGREEMENT_TEXT, AnalyzedDocumentType.BILATERAL_AGREEMENT
    )
    assert fields["organization_name"] == "Sample Regional Development Authority"
    assert fields["platform_name"] == "Paymir"
    # Exact match, not a substring check -- tightened 2026-08-26 alongside
    # the intervening-stamp-page test below; a substring check here is
    # exactly what let the trailing-noise bug in that scenario go uncaught.
    assert fields["transaction_charges"] == (
        "Amount in PKR (Transaction Range)\n"
        "Transaction Charges (Including 1-LINK)\n"
        "PKR 1-10,000\n"
        "PKR 25.00 per transaction"
    )
    assert "account_holder" not in fields
    assert fields["account_number"] == "PK98FAKE00012345678901"
    assert fields["iban"] == "PK98FAKE00012345678901"
    assert fields["effective_date"] == "2026-03-09"


def test_extract_bilateral_agreement_fields_unfilled_date_is_honest_miss():
    """The real template's execution-date clause is sometimes left blank
    (confirmed real, one of the two real samples) -- must honestly miss
    rather than guess a date, while every other field is unaffected."""
    fields = extract_fields(
        BILATERAL_AGREEMENT_TEXT_UNFILLED_DATE, AnalyzedDocumentType.BILATERAL_AGREEMENT
    )
    assert "effective_date" not in fields
    assert fields["organization_name"] == "Sample Regional Development Authority"
    assert fields["account_number"] == "PK98FAKE00012345678901"


def test_extract_bilateral_agreement_transaction_charges_stops_before_intervening_stamp_page():
    """transaction_charges must stop at the real fee table's end, not trail
    into a second e-stamp/STAMPING cover page bound mid-Section-5 -- a real
    structural pattern on both real Bilateral samples, confirmed live on
    application 20322 document 42978 (2026-08-26). Exact-match, not a
    substring check: the original 2026-08-22 test only asserted
    "PKR 25.00 per transaction" in the value, which stayed true whether or
    not an entire stamp page of noise came along with it -- this is why the
    trailing-noise bug went uncaught until a real live pipeline run surfaced
    it.
    """
    fields = extract_fields(
        BILATERAL_AGREEMENT_TEXT_WITH_INTERVENING_STAMP_PAGE,
        AnalyzedDocumentType.BILATERAL_AGREEMENT,
    )
    # 2026-08-26: the CamScanner watermark ("CS"/"CamScanner") that precedes
    # every page's boundary in all 3 real samples is now stripped as a
    # post-processing cleanup -- see _strip_trailing_scanner_watermark.
    assert fields["transaction_charges"] == (
        "Amount in PKR (Transaction Range)\n"
        "Transaction Charges (Including 1-LINK)\n"
        "PKR 1-10,000\n"
        "PKR 25.00 per transaction"
    )
    for noise in ("STAMPING", "Non-Judicial", "Vendor Information", "Sample Vendor", "CamScanner"):
        assert noise not in fields["transaction_charges"]
    # Every other field must still extract correctly -- the intervening page
    # must not disturb anything upstream of the fee table.
    assert fields["organization_name"] == "Sample Regional Development Authority"
    assert fields["platform_name"] == "Paymir"


def test_bilateral_agreement_validators_and_scoring():
    document_type = AnalyzedDocumentType.BILATERAL_AGREEMENT
    fields = extract_fields(BILATERAL_AGREEMENT_TEXT, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["account_number"]["status"] == "valid"
    assert by_field["iban"]["status"] == "valid"
    assert by_field["effective_date"]["status"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_authority_letter_fields_comma_form():
    fields = extract_fields(
        AUTHORITY_LETTER_TEXT_COMMA_FORM, AnalyzedDocumentType.AUTHORITY_LETTER
    )
    assert fields["focal_person_name"] == "Naveed Khan"
    assert fields["focal_person_designation"] == "Deputy Director Administration"
    assert fields["organization_name"] == "SAMPLE DIRECTORATE GENERAL"


def test_extract_authority_letter_fields_paren_form():
    fields = extract_fields(
        AUTHORITY_LETTER_TEXT_PAREN_FORM, AnalyzedDocumentType.AUTHORITY_LETTER
    )
    assert fields["focal_person_name"] == "Salman Raza"
    assert fields["focal_person_designation"] == "Assistant Finance Officer"
    assert fields["organization_name"] == "TMA Sample District"


def test_authority_letter_validators_and_scoring():
    document_type = AnalyzedDocumentType.AUTHORITY_LETTER
    fields = extract_fields(AUTHORITY_LETTER_TEXT_COMMA_FORM, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    # No account fields in this real-shaped fixture -- must be reported
    # missing, not invalid, and must not force a critical failure (they are
    # deliberately not critical fields for this type).
    assert by_field["account_number"]["status"] == "missing"
    assert by_field["iban"]["status"] == "missing"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_account_maintenance_certificate_fields():
    fields = extract_fields(
        ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
    assert fields["account_number"] == "01234567890123"
    assert fields["iban"] == "PK36FUTB0000001123456702"
    assert fields["bank_name"] == "Future Bank Limited"
    assert fields["branch_name"] == "Main Branch, Peshawar"
    assert fields["issue_date"] == "2026-08-15"


def test_extract_tripartite_agreement_fields():
    fields = extract_fields(
        TRIPARTITE_AGREEMENT_TEXT,
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    assert fields["party_1link"] == "1-Link (Private) Limited"
    assert fields["party_kpitb"] == "Khyber Pakhtunkhwa Information Technology Board"
    assert fields["party_subbiller"] == "Transport and Mass Transit Department"
    assert fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
    assert fields["account_number"] == "01234567890123"
    assert fields["branch_code"] == "Main Branch, Peshawar"


#: Synthetic fixture mirroring the compound-document table layout found in
#: TMA Thall Agreement.docx (2026-08-20): the Tripartite section appears as a
#: signature table (parties listed in columns) followed by an account/fee table,
#: with no labeled "Account Number: <value>" block -- the account number sits in
#: the last column of a "Sr No | Bank Name | Account No" table row instead.
#: Fabricated data (PK99FAKE IBAN) -- never real extracted values.
TRIPARTITE_AGREEMENT_COMPOUND_TABLE_TEXT = """\
1. | For & Behalf of | 2 | For & Behalf of | 3 | For & Behalf of
1 LINK (Pvt) Limited | Fake Municipal Administration | Khyber Pakhtunkhwa Information & Technology Board (KP-ITB)
Name:
Designation:
CNIC: | Name:
Designation:
CNIC: | Name:
Designation:

Amount in PKR (Transaction Range) | Transaction Charges (Including 1-LINK)
PKR 1-10,000 | PKR 25.00 per transaction

Sr No | Bank Name | Account No
01 | Bank of Fake Branch | PK99FAKE00012345678901
"""


def test_extract_tripartite_agreement_compound_table_layout():
    """account_number must be extracted from a pipe-separated table row (not a
    labeled-block). Validated on n=1 real sample (TMA Thall Agreement.docx,
    2026-08-20) -- an unusually messy compound doc, not a clean split page.
    The party_1link fix (spaced '1 LINK') and party_kpitb fix (optional '&')
    are also exercised here.
    """
    fields = extract_fields(
        TRIPARTITE_AGREEMENT_COMPOUND_TABLE_TEXT,
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    # 1 LINK (with space) must now be recognised
    assert "1 LINK" in fields.get("party_1link", ""), (
        f"party_1link should contain '1 LINK'; got {fields.get('party_1link')!r}"
    )
    # KPITB with & variant must now be recognised
    assert (
        "Khyber Pakhtunkhwa Information" in fields.get("party_kpitb", "")
        or fields.get("party_kpitb") == "KP-ITB"
    ), f"party_kpitb not extracted; got {fields.get('party_kpitb')!r}"
    # Table-row account number (PK99FAKE...) must be extracted
    assert fields.get("account_number") == "PK99FAKE00012345678901", (
        f"account_number: expected 'PK99FAKE00012345678901'; got {fields.get('account_number')!r}"
    )

#: Synthetic (fabricated, non-real) fixtures for the structural bank-account
#: block parser, mirroring the real OCR layouts confirmed in Confidential Data/
#: (see the extractor docstrings). Every account number / IBAN / CNIC below is
#: invented; the "PK99FAKE..." IBAN shape keeps the values unambiguously fake.
#: The column-table shape comes from TMA Lal Dir Upper (header block mapped
#: positionally onto the value block, with an OCR-noise header line), the
#: interleaved/dotted-leader/wrapped shapes from the four GDA Abbotabad AMC
#: copies (Allied, ZTBL, NBP, BOK).
TRIPARTITE_COLUMN_TABLE_TEXT = """TRIPARTITE AGREEMENT
This Tripartite Agreement is made and entered into by and between:
1-Link (Private) Limited, ... (hereinafter referred to as '1-Link')
Bank details shall be maintained as follows:
S#
Bank Name
IENT
Account Title
IBAN/Account No
01
Sample Bank Branch
Sample Regional Development Authority
PK99FAKE0000000000000000
Branch (0312)
"""

DOTTED_LEADER_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
ACCOUNT NUMBER:... 00112233445566
Title of AccOunt: SAMPLE DEVELOPMENT AUTHORITY.
IBAN:PK99FAKE0000000000000000...
"""

COMBINED_VALUE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the following account is maintained with us:
Title of Account
SAMPLE AUTHORITY
Account No/IBAN
00112233445566/PK99FAKE0000000000000000
Date of Account Opening
01 JANUARY 2000
"""

WRAPPED_TITLE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
TITLE OF ACCOUNT
SAMPLE AUTHORITY (SAMPLE REGIONAL
DEVELOPMENT
FUND)
CNIC OF AUTHORIZED SIGNATORY
12345-1234567-1
ACCOUNT NO
1234567890
ACCOUNT NO/IBAN
PK99FAKE0000000000000000
"""

FIRST_MATCH_WINS_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
ACCOUNT NUMBER:... 00112233445566
Title of AccOunt: FIRST PAGE AUTHORITY.
IBAN:PK99FAKE0000000000000000...
--- page break ---
Account Title
SECOND PAGE AUTHORITY
Account NO.
PK88FAKE0000000000000000
"""

ROW_INDEX_GUARD_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account Title
Sample Authority
Account No
01
Account Status
Active
"""

PARTIAL_CERT_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account Title: SAMPLE AUTHORITY
"""

PARENTHETICAL_LABEL_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Title of Account
SAMPLE AUTHORITY
Account No. (T-24 System)
00112233445566
IBAN: PK99FAKE0000000000000000
"""

PARENTHETICAL_LABEL_INLINE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account Title: SAMPLE AUTHORITY
Account No. (T-24 System): 00112233445566
"""

PAREN_IBAN_INLINE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
Account No.: PK99FAKE0000000000000000
"""

PARALLEL_GENERATIONS_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the account of SAMPLE SPORTS AUTHORITY maintained
with this branch is in good standing.
Account No. (T-24 System)
00112233445566
Account No. (CBS)
00112233445567
Account No. (Core Banking)
00112233445568
"""

SENTENCE_NO_OWNERSHIP_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the following account is maintained with us.
Account No.
00112233445566
"""

PAREN_IBAN_OCR_NOISE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that the following account is maintained with us.
account number (1BAN) PK99FAKE0000000000000000 titled as Tehsil General Account
Account Title
SAMPLE AUTHORITY
"""

SUBJECT_VERB_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
It is certified that SAMPLE SPORTS AUTHORITY maintaining account with SAMPLE
BANK Mandian Branch (1234) as per below mentioned details.
ACCOUNT NO
00112233445566
"""

SUBJECT_VERB_IS_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that SAMPLE SPORTS AUTHORITY is maintaining a current
account with our bank.
ACCOUNT NO
00112233445566
"""

SUBJECT_VERB_TITLE_CASE_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that Sample Sports Complex is maintaining a current account
at The Bank of Khyber since 01-01-2000. Following are the account details:
ACCOUNT NO
00112233445566
"""

WE_ARE_MAINTAINING_SENTENCE_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
We are maintaining the above mentioned account in our branch.
ACCOUNT NO
00112233445566
"""

BALANCED_PAREN_TITLE_STOP_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
TITLE OF ACCOUNT
SAMPLE SPORTS (SAMPLE DEVELOPMENT
AUTHORITY)
SAMPLE FUND
CNIC OF AUTHORIZED SIGNATORY
12345-1234567-1
ACCOUNT NO
1234567890
"""

PREFIXED_GENERATIONS_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that SAMPLE SPORTS COMPLEX is maintaining a BOK Saving Account at The Bank of
Khyber, Main Corporate Branch Peshawar. Following are the account details:
Old Account No (U-Bank Plus)
00112233445560
Old IBAN No. (U-Bank Plus)
PK99FAKE0100010200000001
Account No. (T-24 System)
00112233445561
IBAN No. (T-24 System)
PK99FAKE0200010000000001
New Account No. (T-24 Islamic)
00112233445562
New IBAN No. (T-24 Islamic)
PK99FAKE0300010000000001
"""

OLD_PREFIX_BEFORE_ANCHORED_TEXT = """ACCOUNT MAINTENANCE CERTIFICATE
This is to certify that SAMPLE SPORTS COMPLEX is maintaining a BOK Saving Account at The Bank of
Khyber, Main Corporate Branch Peshawar. Following are the account details:
Old Account No (U-Bank Plus)
00112233445560
Account No. (T-24 System)
00112233445561
IBAN No. (T-24 System)
PK99FAKE0200010000000001
"""


def test_extract_tripartite_column_table_positions_values_by_header():
    # The real Tripartite layout is a stacked column table whose header block
    # ("S# / Bank Name / IENT / Account Title / IBAN/Account No") maps
    # positionally onto the value block. The OCR-noise "IENT" header must not
    # shift the mapping, the row index "01" must not become the account number,
    # and the IBAN-only value in the account slot must be promoted to
    # account_number (Tripartite has no separate iban field).
    fields = extract_fields(
        TRIPARTITE_COLUMN_TABLE_TEXT,
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    assert fields["account_holder"] == "Sample Regional Development Authority"
    assert fields["account_number"] == "PK99FAKE0000000000000000"
    assert "iban" not in fields


def test_extract_dotted_leader_same_line_values():
    # ZTBL's AMC uses "Label:... value" dotted leaders; trailing separator dots
    # on the IBAN value are OCR noise and must be stripped.
    fields = extract_fields(
        DOTTED_LEADER_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE DEVELOPMENT AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_combined_account_number_iban_value():
    # Allied's AMC lists "Account No/IBAN" with a combined "<number>/<IBAN>"
    # value that must be split into the two fields.
    fields = extract_fields(
        COMBINED_VALUE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_wrapped_multiline_account_title():
    # NBP's AMC wraps the account title across three OCR lines; capture must
    # join them and stop before the next field's label ("CNIC OF AUTHORIZED
    # SIGNATORY"), while the later IBAN-only "ACCOUNT NO/IBAN" value must feed
    # the iban field, not overwrite the plain account number.
    fields = extract_fields(
        WRAPPED_TITLE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == (
        "SAMPLE AUTHORITY (SAMPLE REGIONAL DEVELOPMENT FUND)"
    )
    assert fields["account_number"] == "1234567890"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_first_page_value_wins_over_later_page():
    # ZTBL's page 1 and NRSP's page 2 both state account details for the same
    # document; the page-1 values must win (first match in document order), so
    # the account number is never the page-2 IBAN-shaped value.
    fields = extract_fields(
        FIRST_MATCH_WINS_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "FIRST PAGE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_row_index_never_becomes_account_number():
    # An all-digit value of length <= 3 (a table row index / page marker) must
    # never be captured as the account number -- the shape guard rejects it,
    # which generalizes across row indices 01/02/03 rather than blacklisting a
    # specific value.
    fields = extract_fields(
        ROW_INDEX_GUARD_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "Sample Authority"
    assert "account_number" not in fields
    assert "iban" not in fields


def test_extract_partial_certificate_missing_fields_are_absent():
    # A certificate that genuinely carries no account number must report the
    # field as absent rather than fabricate one.
    fields = extract_fields(
        PARTIAL_CERT_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert "account_number" not in fields
    assert "iban" not in fields


def test_extract_parenthetical_label_value_on_next_line():
    # The real DG_Sports AMC labels its account number "Account No. (T-24
    # System)" -- a parenthetical naming the bank system. The qualifier must be
    # consumed into the label (not mistaken for an inline value) so the number
    # on the following line is captured.
    fields = extract_fields(
        PARENTHETICAL_LABEL_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_parenthetical_label_inline_value_after_colon():
    # The same qualifier shape with the value on the same line after a colon
    # must also extract, and a parenthetical IBAN value must never be eaten by
    # the qualifier-stripping rule.
    fields = extract_fields(
        PARENTHETICAL_LABEL_INLINE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE AUTHORITY"
    assert fields["account_number"] == "00112233445566"
    fields = extract_fields(
        PAREN_IBAN_INLINE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_first_of_parallel_account_generations():
    # The real DG_Sports AMC certifies the account under three parallel bank
    # systems (T-24, CBS, Core), each its own labeled block, and states the
    # holder only in prose -- never as its own field. The first valid account
    # number in document order wins, and the sentence-level fallback recovers
    # the holder.
    fields = extract_fields(
        PARALLEL_GENERATIONS_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS AUTHORITY"
    assert fields["account_number"] == "00112233445566"


def test_extract_skips_old_and_new_prefixed_generation_labels():
    # The real DG_Sports AMC's first and third generation labels are prefixed
    # with "Old"/"New" ("Old Account No (U-Bank Plus)", "New Account No.
    # (T-24 Islamic)") -- they must NOT be read as the anchored account-number
    # label (the anchor pattern matches from the start of the line, so "Old
    # Account No" and "New Account No" do not match it), and their values must
    # not be captured. The first genuinely anchored "Account No. (T-24
    # System)" block wins, and its IBAN must come from that same generation
    # (not an older/newer one).
    fields = extract_fields(
        PREFIXED_GENERATIONS_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS COMPLEX"
    assert fields["account_number"] == "00112233445561"
    assert fields["iban"] == "PK99FAKE0200010000000001"


def test_extract_old_prefixed_block_before_anchored_block_does_not_win():
    # Even when an "Old Account No (U-Bank Plus)" block appears BEFORE the
    # genuinely anchored "Account No." block in document order, the prefixed
    # label is not an account-number anchor, so the anchored block still wins.
    # This pins the real DG_Sports shape: the old-generation value must never
    # leak in as the account number.
    fields = extract_fields(
        OLD_PREFIX_BEFORE_ANCHORED_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS COMPLEX"
    assert fields["account_number"] == "00112233445561"
    assert fields["iban"] == "PK99FAKE0200010000000001"


def test_extract_holder_from_sentence_only_no_false_positive():
    # The sentence fallback must not fire on prose that merely mentions the
    # word "account" without ownership ("account is maintained with us") and
    # must not surface a placeholder or bank-name noise as the holder.
    fields = extract_fields(
        SENTENCE_NO_OWNERSHIP_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_number"] == "00112233445566"
    assert "account_holder" not in fields


def test_extract_account_number_from_ocr_noise_prose_tail():
    # A qualifier-stripped OCR line whose trailing prose ("...titled as Tehsil
    # General Account") is not part of the number must still yield the real
    # IBAN-shaped token, never a prose-laden account_number value.
    fields = extract_fields(
        PAREN_IBAN_OCR_NOISE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_number"] == "PK99FAKE0000000000000000"
    assert fields["iban"] == "PK99FAKE0000000000000000"


def test_extract_holder_from_subject_verb_sentence():
    # The real DG_Sports/GDA AMC certifying sentence states the holder as the
    # subject ("It is certified that [ORG] maintaining account with ..."),
    # opposite word order from the "account of X" patterns. The subject-verb
    # pattern must recover it when no labeled holder exists.
    fields = extract_fields(
        SUBJECT_VERB_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS AUTHORITY"
    assert fields["account_number"] == "00112233445566"


def test_extract_holder_from_is_maintaining_sentence():
    # The same subject-verb shape with an explicit "is" ("... is maintaining a
    # ... Account") must also match.
    fields = extract_fields(
        SUBJECT_VERB_IS_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS AUTHORITY"
    assert fields["account_number"] == "00112233445566"


def test_extract_holder_from_title_case_subject_verb_sentence():
    # The real DG_Sports AMC states the holder in Title Case ("certify that
    # Sample Sports Complex is maintaining ...") with no labeled holder field;
    # the sentence capture must accept mixed-case names, not just ALL-CAPS.
    fields = extract_fields(
        SUBJECT_VERB_TITLE_CASE_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "Sample Sports Complex"
    assert fields["account_number"] == "00112233445566"


def test_extract_holder_sentence_rejects_bank_as_subject():
    # "We are maintaining the above mentioned account in our branch" names no
    # holder; the subject is the bank/branch itself, which the sentence path
    # must not surface as an account holder (labeled titles are unaffected).
    fields = extract_fields(
        WE_ARE_MAINTAINING_SENTENCE_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_number"] == "00112233445566"
    assert "account_holder" not in fields


def test_extract_wrapped_parenthetical_title_stops_at_balance():
    # A wrapped parenthetical title is complete once its closing paren is
    # consumed; a trailing unrelated all-caps line must not be absorbed.
    # (GDA copy3's "DG GDA (GALIYAT DEVELOPMENT AUTHORITY)" followed by
    # "DEVELOPMENT FUND".)
    fields = extract_fields(
        BALANCED_PAREN_TITLE_STOP_TEXT,
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "SAMPLE SPORTS (SAMPLE DEVELOPMENT AUTHORITY)"
    assert "SAMPLE FUND" not in fields["account_holder"]
    assert fields["account_number"] == "1234567890"


def test_checklist_field_labels_never_route_into_keyword_detection():
    # The Account Maintenance Certificate's own field labels ("IBAN",
    # "Account Number") are close enough to the bank-statement keyword table
    # that OCR keyword detection misclassifies it. This is exactly why the
    # service routes checklist types from the splitter's own classification
    # *before* keyword detection -- so the assertion below documents the
    # hazard rather than the expected classification.
    assert (
        detect_document_type(ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT)
        is not AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    )


def test_extract_brd_fields_prose_form():
    fields = extract_fields(
        BRD_TEXT_PROSE_FORM, AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert fields["revenue_services_listed"] == (
        "prescribed fees at each facility office.\n"
        "For ease and transparency, this office is already collaborating with KPITB\n"
        "on a Management Information System and plans to integrate digital payment\n"
        "solutions through KPITB's FinTech Unit within the system."
    )


def test_extract_brd_fields_numbered_list_form():
    fields = extract_fields(
        BRD_TEXT_NUMBERED_LIST_FORM,
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FIN TECH UNIT"
    assert fields["revenue_services_listed"] == (
        "sources of Income of this TMA are:\n"
        "1. General Bus Stand\n"
        "2. Cattle Fair Sample\n"
        "3. Service Fee\n"
        "INTENTION TO ON-BOARD DEPARTMENT FOR THE ENABLEMENT OF THE DIGITAL\n"
        "PAYMENTS VIA KPITB's FIN TECH UNIT\n"
        "This Office intends to go towards Digital Payments via KPITB'S FIN TECH\n"
        "UNIT."
    )


def test_extract_brd_fields_categorized_bullets_form():
    fields = extract_fields(
        BRD_TEXT_CATEGORIZED_BULLETS_FORM,
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert fields["revenue_services_listed"] == (
        "SERVICES OFFERED:\n"
        "Revenue Collection\n"
        "Taxes (Property Tax, Water Tax)\n"
        "Miscellaneous (Registration Fee, Lease Renewal, Rents)\n"
        "4. Intention to on-board department for the enablement of the digital\n"
        "payments via KPITB's FinTech Unit\n"
        "The Authority intends to collaborate with KPITB's FinTech Unit to digitize\n"
        "all revenue streams."
    )


def test_brd_missing_digitization_mention_is_missing_not_invalid():
    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    fields = extract_fields(BRD_TEXT_NO_DIGITIZATION_MENTION, document_type)
    assert "digitization_intent_confirmed" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["digitization_intent_confirmed"]["status"] == "missing"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # digitization_intent_confirmed is critical -- its absence must force
    # manual review, not a silent pass.
    assert status is VerificationStatus.NEEDS_REVIEW


def test_brd_missing_services_list_is_visible_but_not_blocking():
    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    fields = extract_fields(BRD_TEXT_NO_SERVICES_MENTION, document_type)
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert "revenue_services_listed" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    # revenue_services_listed is non-critical, but Section 10 requires it --
    # its absence must still surface to a reviewer as "missing", not vanish
    # from the results just because it isn't critical.
    assert by_field["revenue_services_listed"]["status"] == "missing"
    assert by_field["digitization_intent_confirmed"]["status"] == "valid"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # Non-critical, so this alone must not force NEEDS_REVIEW -- but it must
    # still cost something: not a full VERIFIED pass either.
    assert status is not VerificationStatus.NEEDS_REVIEW
    assert status is not VerificationStatus.VERIFIED


def test_brd_validators_and_scoring():
    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT
    fields = extract_fields(BRD_TEXT_NUMBERED_LIST_FORM, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result for result in validations}
    assert by_field["digitization_intent_confirmed"]["status"] == "valid"
    assert by_field["revenue_services_listed"]["status"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no consistency rules registered yet for this type

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score > 0.0
    assert status is not VerificationStatus.FAILED


def test_extract_onelink_letter_fields_single_account_form():
    # branch_code and iban were both deliberately dropped from this
    # extractor 2026-08-19 (department decision, see CONTEXT.md) -- kept as
    # a real, distinct fixture only to confirm organization_name still
    # extracts cleanly from this shape and nothing else is invented.
    fields = extract_fields(
        ONE_LINK_LETTER_TEXT_SINGLE_ACCOUNT, AnalyzedDocumentType.ONE_LINK_LETTER
    )
    assert fields["organization_name"] == "SAMPLE TEHSIL MUNICIPAL ADMINISTRATION"
    assert "branch_code" not in fields


def test_extract_onelink_letter_fields_multi_bank_table_form():
    document_type = AnalyzedDocumentType.ONE_LINK_LETTER
    fields = extract_fields(ONE_LINK_LETTER_TEXT_MULTI_BANK_TABLE, document_type)
    assert fields["organization_name"] == "SAMPLE DEVELOPMENT AUTHORITY"
    assert "branch_code" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["organization_name"] == "valid"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    assert status is not VerificationStatus.NEEDS_REVIEW


def test_onelink_letter_missing_organization_name_forces_review():
    document_type = AnalyzedDocumentType.ONE_LINK_LETTER
    fields = extract_fields(ONE_LINK_LETTER_TEXT_NO_ORG_NAME, document_type)
    assert "organization_name" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["organization_name"] == "missing"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # organization_name is critical -- its absence must force manual review.
    assert status is VerificationStatus.NEEDS_REVIEW


def test_onelink_letter_validators_and_scoring():
    document_type = AnalyzedDocumentType.ONE_LINK_LETTER
    fields = extract_fields(ONE_LINK_LETTER_TEXT_SINGLE_ACCOUNT, document_type)
    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["organization_name"] == "valid"

    consistency = RulesEngine().run(document_type, fields)
    assert consistency == []  # no cross-document rule watches this type's fields

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score == 1.0
    assert status is VerificationStatus.VERIFIED


def test_extract_cnic_front_fields_clean_layout():
    fields = extract_fields(CNIC_FRONT_TEXT_CLEAN, AnalyzedDocumentType.CNIC_FRONT)
    assert fields["document_number"] == "12345-1234567-1"
    assert fields["full_name"] == "Samia Naz"
    assert fields["date_of_expiry"] == "2030-01-01"


def test_extract_cnic_front_fields_scrambled_layout():
    document_type = AnalyzedDocumentType.CNIC_FRONT
    fields = extract_fields(CNIC_FRONT_TEXT_SCRAMBLED, document_type)
    # document_number (format-anchored) and full_name (lucky adjacency, same
    # as the real scrambled sample) still extract correctly.
    assert fields["document_number"] == "12345-1234567-1"
    assert fields["full_name"] == "Samia Naz"
    # date_of_expiry's two-label/two-value block never occurs intact here --
    # must honestly miss, not guess from out-of-order values.
    assert "date_of_expiry" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["date_of_expiry"] == "missing"
    assert by_field["document_number"] == "valid"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # date_of_expiry is non-critical, so its absence alone must not force review.
    assert status is not VerificationStatus.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# Real-sample regression tests
#
# Everything above this point runs against hand-written literal fixtures --
# useful for exercising specific structural shapes in isolation, but every one
# of them was written by transcribing what a real cached sample looked like at
# some point, never by loading the real file itself. That gap is exactly what
# let the transaction_charges page-separator bug (fixed in 5914a5a) go
# unnoticed: the fixtures never exercised real production-shaped text, so a
# passing test suite gave no signal either way. Audited 2026-08-26 (see
# CONTEXT.md) and closed here for the 8 document types that currently have at
# least one real cached sample on file.
#
# These tests read directly from Confidential Data/.ocr_cache/*.txt -- a
# gitignored, local-only directory of real onboarding OCR text (PII: names,
# CNICs, IBANs) that does not exist in CI or on a fresh checkout. They are
# skipped, not failed, when it is absent, exactly like every other real-sample
# validation workflow in this project (see scripts/ocr_cache.py's own
# module docstring). A direct file read is used rather than
# scripts.ocr_cache.get_ocr_text(): every file referenced below is already
# cached (a cache hit reads instantly either way), and a direct read avoids
# pulling in that module's pymupdf/PaddleOCREngine/DocumentSplitter import
# chain for what is otherwise a plain text-fixture test.
#
# IMPORTANT CAVEAT: each cached file pins one specific OCR pass of one real
# document, not a guarantee of what a fresh live OCR of the same physical
# document would always produce byte-for-byte. Document 42978's own cache
# entry (see the transaction_charges fix) already showed genuine wording
# differences between two separate OCR runs of the identical physical page.
# A passing test here means "this extractor handles this specific captured
# text correctly today," not "this extractor will always handle this
# document identically on every future OCR pass."
_CONFIDENTIAL_DATA = Path(__file__).resolve().parents[2] / "Confidential Data"
_OCR_CACHE_DIR = _CONFIDENTIAL_DATA / ".ocr_cache"

requires_real_cache = pytest.mark.skipif(
    not _OCR_CACHE_DIR.is_dir(),
    reason=(
        "Confidential Data/.ocr_cache not present (gitignored, real onboarding "
        "OCR samples) -- these regression tests only run where it exists, e.g. "
        "local dev, not CI."
    ),
)


def _real_cache_text(filename: str) -> str:
    return (_OCR_CACHE_DIR / filename).read_text(encoding="utf-8")


#: Document types with a real extractor (app/document_analysis/services.py's
#: _CHECKLIST_TYPE_MAP) but zero real cached samples anywhere in
#: Confidential Data/.ocr_cache/ as of this audit (2026-08-26) -- generic
#: extractors reachable only via detect_document_type's independent keyword
#: scorer, never through the real onboarding checklist/splitter routing, so
#: no real onboarding document has ever exercised them. A genuine "needs more
#: real samples" gap, not something to fabricate a synthetic fixture for and
#: call real coverage: BANK_STATEMENT, PAYSLIP, ID_DOCUMENT, TAX_DOCUMENT.


@requires_real_cache
def test_real_bilateral_agreement_combined_kp_ppra_test():
    """Document 42978's own cache entry (application 20322) -- the real
    production-PAGE_SEPARATOR-shaped sample the transaction_charges fix was
    built and verified against. Kept here as the permanent regression test
    for that fix, not just a one-off verification script."""
    fields = extract_fields(
        _real_cache_text("combined_kp_ppra_test__BILATERAL_AGREEMENT_copy1.txt"),
        AnalyzedDocumentType.BILATERAL_AGREEMENT,
    )
    assert fields["organization_name"] == "Khyber Pakhtunkhwa Private Schools Regulatory Authority"
    assert fields["platform_name"] == "Paymir"
    assert fields["transaction_charges"] == (
        "Amount in PKR (Transaction Range)\n"
        "Transaction Charges (Including 1-LINK)\n"
        "PKR 1-10,000\n"
        "PKR 25.00 per transaction\n"
        "PKR 10,001-100,000\n"
        "PKR 50.00 per transaction\n"
        "PKR 100,001-250,000\n"
        "PKR 80.00 per transaction\n"
        "PKR 250,001-1,000,000\n"
        "PKR 155.00 per transaction\n"
        "PKR 1,000,001-2,500,000\n"
        "PKR 280.00 per transaction\n"
        "PKR 2,500,001-5,000,000\n"
        "PKR 405.00 per transaction\n"
        "PKR 5,000,001-Above\n"
        "PKR 535.00 per transaction"
    )
    assert "CamScanner" not in fields["transaction_charges"]
    assert "STAMPING" not in fields["transaction_charges"]
    assert fields["account_number"] == "PK51KHYB0015002000883401"
    assert fields["iban"] == "PK51KHYB0015002000883401"


@requires_real_cache
def test_real_bilateral_agreement_conservator_wildlife():
    """No intervening stamp page on this real sample -- transaction_charges
    naturally runs into a trailing paragraph of prose before the next
    section, which is correct real content, not noise to strip."""
    fields = extract_fields(
        _real_cache_text("Conservator_Wildlife_Peshawar_Zoo__BILATERAL_AGREEMENT_copy1.txt"),
        AnalyzedDocumentType.BILATERAL_AGREEMENT,
    )
    assert fields["organization_name"] == "Director/Conservator Wildlife Peshawar Zoo"
    assert fields["platform_name"] == "Paymir"
    assert fields["transaction_charges"].startswith(
        "Amount in PKR (Transaction Range)\nTransaction Charges (Including 1-LINK)"
    )
    assert fields["transaction_charges"].endswith(
        "If per transaction charges are updated by the 1-Link, KPITB will intimate "
        "the variations\nin rates to Director/Conservator Wildlife Peshawar Zoo."
    )
    assert fields["account_number"] == "PK20ABPA0010084429570010"
    assert fields["iban"] == "PK20ABPA0010084429570010"
    assert fields["effective_date"] == "2026-05-11"


@requires_real_cache
def test_real_bilateral_agreement_schedule_of_charges():
    """Cached under OTHER_SUPPORTING_DOCUMENT in its filename (a stale
    artifact of the splitter misrouting this exact file before the
    2026-08-26 title-match fix, see CONTEXT.md) -- its real content is a
    genuine Bilateral Agreement, the second of the two originally
    2026-08-22-validated real samples. Read and fed to the extractor
    directly by content, not by filename, so the stale type label in the
    cache key does not matter here."""
    fields = extract_fields(
        _real_cache_text("schdule_of_charges_or_bilateral__OTHER_SUPPORTING_DOCUMENT_copy1.txt"),
        AnalyzedDocumentType.BILATERAL_AGREEMENT,
    )
    assert fields["organization_name"] == "Khyber Pakhtunkhwa Private Schools Regulatory Authority"
    assert fields["platform_name"] == "Paymir"
    assert "CamScanner" not in fields["transaction_charges"]
    assert fields["account_number"] == "PK51KHYB0015002000883401"
    assert fields["iban"] == "PK51KHYB0015002000883401"


@requires_real_cache
def test_real_authority_letter_gda_abbotabad():
    """The "Dr." honorific / designation-on-next-line / "this Authority"
    backward-reference letterhead-fallback case (2026-08-19 fixes)."""
    fields = extract_fields(
        _real_cache_text("GDA_Abbotabad__AUTHORITY_LETTER_copy1.txt"),
        AnalyzedDocumentType.AUTHORITY_LETTER,
    )
    assert fields["focal_person_name"] == "Samar Hayat Khan"
    assert fields["focal_person_designation"] == "Taxation Officer-I"
    assert fields["organization_name"] == "Galiyat Development Authority, Abbottabad"


@requires_real_cache
def test_real_authority_letter_tma_samarbagh():
    """The bare "on behalf of the\\nAuthority" backward-reference case
    (2026-08-20 fix) -- resolves through the same letterhead fallback.

    organization_name was wrong until 2026-08-26: the letterhead's first
    substantive line, "OFFICE OF THE TEHSIL MUNICIPAL OFFICER", is a job
    title, not the real organization name -- confirmed against this same
    department's real ONE_LINK_LETTER sample, which independently states
    the real name. Fixed by skipping the confirmed real job-title heading
    shape and joining the "Administration"-ending candidate with its
    place-name continuation line.
    """
    fields = extract_fields(
        _real_cache_text("TMA_Samarbagh_Dir_Lower__AUTHORITY_LETTER_copy1.txt"),
        AnalyzedDocumentType.AUTHORITY_LETTER,
    )
    assert fields["organization_name"] == "THESIL MUNICIPAL ADMINISTRATION SAMARBAGH DIR LOWER"


@requires_real_cache
def test_real_authority_letter_tma_lal_qilla():
    """The same job-title-heading letterhead-fallback bug as TMA Samarbagh
    above, on an independent second real department -- confirms the fix
    generalizes rather than being tuned to one sample (2026-08-26)."""
    fields = extract_fields(
        _real_cache_text("TMA_Lal_Qilla_Dir_Lower__AUTHORITY_LETTER_copy1.txt"),
        AnalyzedDocumentType.AUTHORITY_LETTER,
    )
    assert fields["organization_name"] == "TEHSIL MUNICIPAL ADMINISTRATION LAL QILA DIR LOWER"


@requires_real_cache
def test_real_authority_letter_dg_sports_bare_directorate_reference():
    """A third real backward-reference shape (2026-08-26): "on the behalf of
    Directorate." -- a bare generic noun with no demonstrative at all,
    unlike "this Authority"/"the Authority". Also exercises the anchor-word
    letterhead search: this letterhead's first substantive line is an
    unrelated slogan ("Sports are essential for the development of a happy,
    healthy & vigorous society"), which the blind first-line fallback would
    have wrongly picked; searching for a line containing "directorate"
    correctly skips past it to the real organization name.
    """
    fields = extract_fields(
        _real_cache_text(
            "DG_Sports_KP_Onboarding_Documents__AUTHORITY_LETTER_copy1.txt"
        ),
        AnalyzedDocumentType.AUTHORITY_LETTER,
    )
    assert fields["focal_person_name"] == "Ishfaq Ahmad"
    assert fields["focal_person_designation"] == "Assistant Director Establishment"
    assert fields["organization_name"] == "DIRECTORATE GENERAL OF SPORTS"


@requires_real_cache
def test_real_authority_letter_tma_lal_dir_upper_ocr_corrupted_tail_is_honest_miss():
    """Not a regex boundary bug: this real sample's "on behalf of" sentence
    itself reads "...Tehsil Municipal Administration Dir please." -- the
    pattern faithfully captures the whole real (OCR'd) sentence up to its
    period. The letterhead ("TEHSIL MUNICIPAL ADMINISTRATION LAL DIR
    UPPER") and this letter's own signature block ("TEHSIL-MUCNICIPAL
    ADMINISTRATION\\nDIR UPPER") both independently confirm the real suffix
    is "DIR UPPER", not "please" -- a genuine OCR misread, not an
    extraction bug. No safe, generalizable pattern exists to strip one
    corrupted trailing word from an otherwise-correct capture without
    overfitting to this exact real artifact (2026-08-26 investigation);
    left as an honest, documented limitation rather than a fabricated fix.
    """
    fields = extract_fields(
        _real_cache_text("TMA_Lal_Dir_Upper__AUTHORITY_LETTER_copy1.txt"),
        AnalyzedDocumentType.AUTHORITY_LETTER,
    )
    assert fields["organization_name"] == "Tehsil Municipal Administration Dir please"


@requires_real_cache
def test_real_authority_letter_tma_thall_hangu_master_checklist_page_is_honest_empty():
    """Not every real page cached under the AUTHORITY_LETTER checklist slot
    is actually an authority letter: this specific real sample is a "MASTER
    CHECK LIST" cover page (a splitter/document-grouping artifact, out of
    scope for this extractor audit -- see CONTEXT.md). Correctly extracts
    nothing, since there is no authorization clause on this page at all --
    an honest empty result, not a bug in the extractor."""
    fields = extract_fields(
        _real_cache_text("TMA_Thall_Hangu__AUTHORITY_LETTER_copy1.txt"),
        AnalyzedDocumentType.AUTHORITY_LETTER,
    )
    assert fields == {}


@requires_real_cache
def test_real_account_maintenance_certificate_gda_abbotabad():
    fields = extract_fields(
        _real_cache_text("GDA_Abbotabad__ACCOUNT_MAINTENANCE_CERTIFICATE_copy1.txt"),
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["branch_name"] == "SUPPLY BAZAR ABD"
    assert fields["account_holder"] == "DIRECTOR GENERAL GDA"
    assert fields["account_number"] == "0010002989240012"
    assert fields["iban"] == "PK68ABPA0010002989240012"
    # The real issue date is present in the source but OCR-mangled into
    # single digits split across consecutive lines, before the "Date of
    # Issue:" label instead of after it -- unrecoverable without a fragile,
    # one-sample-only reconstruction (2026-08-26 investigation; see
    # AccountMaintenanceCertificateExtractor's class docstring). The key is
    # correctly absent, not present with a None value: no date-shaped token
    # exists anywhere in the header zone for this sample.
    assert "issue_date" not in fields


@requires_real_cache
def test_real_account_maintenance_certificate_kppra():
    fields = extract_fields(
        _real_cache_text("account_maintennace_certificate__ACCOUNT_MAINTENANCE_CERTIFICATE_copy1.txt"),
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["branch_name"] == "Civil Secretariat, Peshawar (0015)"
    assert fields["account_holder"] == "KPPRA AUTHORITY FUND ACCOUNT"
    assert fields["account_number"] == "2000876472"
    assert fields["iban"] == "PK21KHYB0015002000876472"
    # Unlabeled -- "18 MAY, 2026" sits alone in the letterhead, before the
    # certifying sentence. Previously missing entirely (2026-08-26 fix):
    # the old pattern required an explicit "Date of Issue"-style label.
    assert fields["issue_date"] == "2026-05-18"


@requires_real_cache
def test_real_account_maintenance_certificate_dg_sports():
    """Unlabeled issue date via the positional header-zone fallback.

    "29-04-2026" sits alone in the letterhead, right after "Bank of Khyber"
    and before the certificate title -- no label at all, the same shape as
    the kppra sample above but with a numeric dash format instead of a
    textual month, confirming the fallback isn't tuned to one format.
    """
    fields = extract_fields(
        _real_cache_text(
            "DG_Sports_KP_Onboarding_Documents__ACCOUNT_MAINTENANCE_CERTIFICATE_copy1.txt"
        ),
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == "Peshawar Sports Complex"
    assert fields["account_number"] == "2000749217"
    assert fields["iban"] == "PK54KHYB0001002000749217"
    assert fields["issue_date"] == "2026-04-29"


@requires_real_cache
def test_real_account_maintenance_certificate_gdc_madyan():
    """Bare "Date:" label (slash format) -- the widened label alternation.

    Previously missing entirely: the old pattern only recognized
    "Date of Issue"/"Issue Date"/"Issued On"/"Issuance Date", not a bare
    "Date:" label, which is how 3 of the 7 real samples actually label it.
    """
    fields = extract_fields(
        _real_cache_text("GDC_Madyan_Swat__ACCOUNT_MAINTENANCE_CERTIFICATE_copy1.txt"),
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["branch_name"] == "IBB MADYAN"
    assert fields["account_holder"] == "GOVT DEGREE COLLEGE MADYAN SWAT"
    assert fields["account_number"] == "3003755532"
    assert fields["iban"] == "PK54KHYB5188003003755532"
    assert fields["issue_date"] == "2026-02-17"


@requires_real_cache
def test_real_account_maintenance_certificate_gda_abbotabad_copy4_ignores_embedded_cnic_date():
    """The header-zone bound's most safety-critical case.

    This real sample embeds a scanned CNIC copy later in the same OCR text,
    which has its own "Date of Issue" field ("23.08.2023") -- a different
    value for an unrelated document. Before 2026-08-26 a whole-document
    search for "Date of Issue" could reach into an embedded document like
    this one; confining the search to the header zone (before the
    certifying sentence) means the real letterhead date ("Dated: April 21,
    2026") is found first and the CNIC's date is never reachable.
    """
    fields = extract_fields(
        _real_cache_text("GDA_Abbotabad__ACCOUNT_MAINTENANCE_CERTIFICATE_copy4.txt"),
        AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    assert fields["account_holder"] == (
        "Director General Galiyat Development Authority Abbottabad"
    )
    assert fields["account_number"] == "3005642921"
    assert fields["iban"] == "PK06KHYB0043000001768004"
    assert fields["issue_date"] == "2026-04-21"


@requires_real_cache
def test_real_tripartite_agreement_tma_thall():
    """The only real Tripartite sample currently on file.

    account_holder was truncated to "TMA T" until 2026-08-26 --
    _HOLDER_SENTENCE_PATTERNS' "on behalf of TMA Thall." match (from an
    Authority Letter section bundled into the same source file) used an
    uppercase-only capture class that stopped dead at the first lowercase
    letter ("Thall" -> "T" then lowercase "h" broke it). Fixed by allowing
    lowercase letters and excluding the literal "." from the class, so the
    match now runs to the real sentence-ending period instead -- "TMA
    Thall". This is not necessarily the bank account's own formal title
    (the real text separately states the account as "...titled as TEHSIL
    GENERAL ACCOUNT TMA THALL" in an unrelated clause the fallback doesn't
    anchor on) -- it is the correct, complete, non-truncated capture of the
    sentence this fallback actually matches; which sentence it should
    prefer is a separate, unrelated scope question, not part of this
    truncation fix.

    party_subbiller was fixed 2026-08-26 (was a known-bad capture of generic
    contract boilerplate -- see CONTEXT.md for the full root cause). The
    document only contains two "(...)" parentheticals mentioning
    "sub-biller" anywhere, and neither names the real sub-biller: one is
    fixed legal boilerplate, the other is the template's own unfilled
    placeholder, "(Sub Biller Name)", never replaced with a real name in
    this signed document. The real name is stated in plain prose instead
    ("The Tehsil Municipal Administration THALL hereby irrevocably
    undertakes..."), confirmed as a stable, reusable template clause across
    11 other real cached files spanning 8+ independent organizations (see
    TripartiteAgreementExtractor's class docstring) -- not single-sample
    evidence, even though this is still the only real sample cached under
    the TRIPARTITE_AGREEMENT type specifically.
    """
    fields = extract_fields(
        _real_cache_text("TMA_Thall_Agreement__TRIPARTITE_AGREEMENT_copy1.txt"),
        AnalyzedDocumentType.TRIPARTITE_AGREEMENT,
    )
    assert fields["party_kpitb"] == "Khyber Pakhtunkhwa Information Technology Board"
    assert fields["account_number"] == "PK82KHYB50130987142561901"
    assert fields["account_holder"] == "TMA Thall"
    assert fields["party_subbiller"] == "The Tehsil Municipal Administration THALL"


@requires_real_cache
def test_real_brd_gda_abbotabad():
    fields = extract_fields(
        _real_cache_text("GDA_Abbotabad__BUSINESS_REQUIREMENT_DOCUMENT_copy1.txt"),
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FinTech Unit"
    assert fields["revenue_services_listed"].startswith("SERVICES OFFERED:")


@requires_real_cache
def test_real_brd_tma_khal_dir_lower():
    fields = extract_fields(
        _real_cache_text("TMA_Khal_Dir_Lower__BUSINESS_REQUIREMENT_DOCUMENT_copy1.txt"),
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == "KPITB's FIN TECH UNIT"
    assert fields["revenue_services_listed"].startswith("sources of Income of this TMA are:")


@requires_real_cache
def test_real_brd_tma_lal_qilla_no_services_list_is_honest_miss():
    """One of two real copies for this org: digitization intent is stated,
    but no services-list anchor phrase appears anywhere on this particular
    page -- an honest miss, not a bug (see BRD_TEXT_NO_SERVICES_MENTION's
    synthetic counterpart above for the same documented behavior)."""
    fields = extract_fields(
        _real_cache_text("TMA_Lal_Qilla_Dir_Lower__BUSINESS_REQUIREMENT_DOCUMENT_copy2.txt"),
        AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    )
    assert fields["digitization_intent_confirmed"] == (
        "Khyber Pakhtunkhwa Information Technology Board\n(KPITB)"
    )
    assert "revenue_services_listed" not in fields


@requires_real_cache
def test_real_one_link_letter_gda_abbotabad():
    fields = extract_fields(
        _real_cache_text("GDA_Abbotabad__ONE_LINK_LETTER_copy2.txt"),
        AnalyzedDocumentType.ONE_LINK_LETTER,
    )
    assert fields["organization_name"] == "GALIYAT DEVELOPMENT AUTHORITY, ABBOTTABAD"


@requires_real_cache
def test_real_one_link_letter_khal_dir_lower():
    """Fixed 2026-08-26 (was truncated to "IL MUNICIPAL ADMINISTRATION
    KHALL" -- see CONTEXT.md). The real text reads "...at their side.
    TEHsIL\\nMUNICIPAL ADMINISTRATION KHALL hereby authorizes 1LINK to take
    actions" -- note the lowercase "s" in "TEHsIL", a real OCR misread of
    one character. organization_name's capture group was uppercase-only
    (``[A-Z][A-Z,.\\s]{3,60}?``), so the lowercase "s" blocked the match
    from starting at "T"; the regex engine's leftmost-match search instead
    found its first valid start two characters later, at "IL", truncating
    the front of the real organization name. Fixed by allowing lowercase
    letters in the class (``[A-Za-z,.\\s]``) -- safe here because the
    capture is still non-greedy with the exact literal "hereby authorizes
    ...to take actions" continuation required immediately after it, so
    widening the class cannot make the match run past the real org name.
    The fixed value below reproduces the source text's own OCR misread
    verbatim ("TEHsIL", not "TEHSIL") -- the fix stops the truncation, it
    does not correct OCR noise that was actually in the document.
    """
    fields = extract_fields(
        _real_cache_text("TMA_Khal_Dir_Lower__ONE_LINK_LETTER_copy3.txt"),
        AnalyzedDocumentType.ONE_LINK_LETTER,
    )
    assert fields["organization_name"] == "TEHsIL MUNICIPAL ADMINISTRATION KHALL"


@requires_real_cache
def test_real_one_link_letter_gda_abbotabad_other_copy_is_honest_empty():
    """This extractor is deliberately narrow (organization_name only, see
    its class docstring) and a real ONE_LINK_LETTER checklist item commonly
    splits into several real cached "copies" (separate pages/sub-documents
    of the same physical form) -- only the specific copy carrying the "(x)
    ... hereby authorizes 1LINK to take actions" clause produces anything.
    This is a different, earlier copy of the same real GDA Abbotabad
    submission that does not carry that clause -- correctly empty, not a
    bug. See CONTEXT.md 2026-08-26 for the fuller finding: roughly 14 of 23
    real ONE_LINK_LETTER cached copies across all organizations on file
    produce zero fields this way, including every copy for some
    organizations entirely -- worth a closer look at whether that is always
    this same honest multi-copy shape or occasionally a real per-org miss,
    but out of scope to chase further in this coverage pass."""
    fields = extract_fields(
        _real_cache_text("GDA_Abbotabad__ONE_LINK_LETTER_copy1.txt"),
        AnalyzedDocumentType.ONE_LINK_LETTER,
    )
    assert fields == {}


@requires_real_cache
def test_real_cnic_front_dg_sports_clean():
    fields = extract_fields(
        _real_cache_text("DG_Sports_KP_Onboarding_Documents__CNIC_FRONT_copy1.txt"),
        AnalyzedDocumentType.CNIC_FRONT,
    )
    assert fields["document_number"] == "14301-0597483-1"
    assert fields["full_name"] == "Tashfeen Haider"
    assert fields["date_of_expiry"] == "2028-10-17"


@requires_real_cache
def test_real_cnic_front_dg_sports_scrambled():
    """The third of DG Sports' three real CNIC samples OCR'd with labels and
    values out of order (see CnicFrontExtractor's class docstring) --
    document_number and full_name still extract correctly, date_of_expiry
    honestly misses since its two-label/two-value block never occurs
    intact here."""
    fields = extract_fields(
        _real_cache_text("DG_Sports_KP_Onboarding_Documents__CNIC_FRONT_copy3.txt"),
        AnalyzedDocumentType.CNIC_FRONT,
    )
    assert fields["document_number"] == "13503-4808137-3"
    assert fields["full_name"] == "Muhammad Arshad Khan"
    assert "date_of_expiry" not in fields


@requires_real_cache
def test_real_formal_request_letter_tma_lal_dir_upper():
    """The only real Formal Request Letter sample currently on file."""
    fields = extract_fields(
        _real_cache_text("TMA_Lal_Dir_Upper__FORMAL_REQUEST_LETTER_copy1.txt"),
        AnalyzedDocumentType.FORMAL_REQUEST_LETTER,
    )
    assert fields["organization_name"] == "TEHSIL MUNICIPAL ADMINISTRATION LAL DIR UPPER"
    assert fields["addressee"] == "The Managing Director"
    assert fields["subject"] == "REQUEST FOR DIGITAL ACCOUNT AND FOR ONLINE PAYMENTS."
    # date is a known, already-documented honest miss on this sample -- see
    # FormalRequestLetterExtractor's class docstring.
    assert "date" not in fields


def test_cnic_front_missing_name_does_not_force_review():
    document_type = AnalyzedDocumentType.CNIC_FRONT
    fields = extract_fields(CNIC_FRONT_TEXT_NO_NAME, document_type)
    assert "full_name" not in fields
    assert fields["document_number"] == "12345-1234567-1"
    assert fields["date_of_expiry"] == "2030-01-01"

    validations = ValidatorEngine().run(document_type, fields)
    consistency = RulesEngine().run(document_type, fields)
    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    # full_name is non-critical -- its absence alone must not force review,
    # even though the fleet-wide field-coverage score dips below VERIFIED.
    assert status is VerificationStatus.PARTIALLY_VERIFIED


def test_cnic_front_missing_document_number_forces_review():
    document_type = AnalyzedDocumentType.CNIC_FRONT
    text = "PAKISTAN\nNational Identity Card\nName\nSamia Naz\n"
    fields = extract_fields(text, document_type)
    assert "document_number" not in fields

    validations = ValidatorEngine().run(document_type, fields)
    by_field = {result["field"]: result["status"] for result in validations}
    assert by_field["document_number"] == "missing"

    *_components_rest, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=RulesEngine().run(document_type, fields),
    )
    # document_number is critical -- its absence must force manual review.
    assert status is VerificationStatus.NEEDS_REVIEW


def test_parse_amount_variants():
    assert _parse_amount("1,250.50") == 1250.5
    assert _parse_amount("1.250,50") == 1250.5
    assert _parse_amount("2,500.00") == 2500.0
    assert _parse_amount("549.75") == 549.75
    assert _parse_amount("EUR 45,000.00") == 45000.0
    assert _parse_amount("1,000") == 1000.0
    assert _parse_amount("0.99") == 0.99
    assert _parse_amount("garbage") is None


# --- Validators --------------------------------------------------------------


def test_validate_iban_valid():
    status, message = validate_iban("DE89370400440532013000")
    assert status == "valid"
    assert "checksum passed" in message


def test_validate_iban_invalid_checksum():
    status, _ = validate_iban("DE89370400440532013001")
    assert status == "invalid"


def test_validate_iban_invalid_format():
    assert validate_iban("12")[0] == "invalid"
    assert validate_iban("DE00")[0] == "invalid"


def test_validate_currency():
    assert validate_currency("EUR")[0] == "valid"
    assert validate_currency("eur")[0] == "invalid"
    assert validate_currency("EURO")[0] == "invalid"


def test_validate_account_number():
    assert validate_account_number("1234567890")[0] == "valid"
    assert validate_account_number("12")[0] == "invalid"
    assert validate_account_number("1234 5678 90")[0] == "valid"


def test_validate_date_accepts_future_expiry():
    assert validate_date("2028-06-01")[0] == "valid"
    assert validate_date("not-a-date")[0] == "invalid"


def test_validate_date_not_future_rejects_future():
    assert validate_date_not_future("1990-05-15")[0] == "valid"
    assert validate_date_not_future("2099-01-01")[0] == "invalid"


def test_validate_salary_month():
    assert validate_salary_month("2026-01")[0] == "valid"
    assert validate_salary_month("2026-13")[0] == "invalid"
    assert validate_salary_month("01/2026")[0] == "invalid"


def test_validator_engine_reports_missing_fields():
    text = """BANK STATEMENT
    Account Number: 1234567890
    Closing Balance: 5,000.00
    """
    document_type, fields, validations, _ = _components(text)
    assert document_type is AnalyzedDocumentType.BANK_STATEMENT
    assert fields["account_number"] == "1234567890"
    statuses = {result["field"]: result["status"] for result in validations}
    assert statuses["account_holder"] == "missing"
    assert statuses["opening_balance"] == "missing"
    assert any(result["message"] == "Account holder missing" for result in validations)


# --- Consistency rules -------------------------------------------------------


def test_rule_reconciliation_passes_with_credits_and_debits():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "pass"


def test_rule_reconciliation_fails_on_mismatch():
    fields = extract_fields(BANK_STATEMENT_TEXT, AnalyzedDocumentType.BANK_STATEMENT)
    fields["closing_balance"] = 9999.99
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "fail"


def test_rule_zero_transactions_keeps_balance():
    text = BANK_STATEMENT_TEXT.replace("Transactions: 23", "Transactions: 0")
    text = text.replace("Total Credits: 2,500.00", "Total Credits: -")
    text = text.replace("Total Debits: 549.75", "Total Debits: -")
    fields = extract_fields(text, AnalyzedDocumentType.BANK_STATEMENT)
    fields["closing_balance"] = fields["opening_balance"]
    results = RulesEngine().run(AnalyzedDocumentType.BANK_STATEMENT, fields)
    reconciliation = next(
        r for r in results if r["rule_id"] == "CLOSING_MATCHES_TRANSACTIONS"
    )
    assert reconciliation["status"] == "pass"


def test_rule_net_le_gross_fails():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    fields["net_salary"] = 99999.0
    results = RulesEngine().run(AnalyzedDocumentType.PAYSLIP, fields)
    assert next(r for r in results if r["rule_id"] == "NET_LE_GROSS")["status"] == "fail"


def test_rule_payment_date_outside_month_fails():
    fields = extract_fields(PAYSLIP_TEXT, AnalyzedDocumentType.PAYSLIP)
    fields["payment_date"] = "2026-06-15"
    results = RulesEngine().run(AnalyzedDocumentType.PAYSLIP, fields)
    rule = next(r for r in results if r["rule_id"] == "PAYMENT_WITHIN_MONTH")
    assert rule["status"] == "fail"


def test_rule_expiry_before_issue_fails():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    fields["issue_date"] = "2030-01-01"
    results = RulesEngine().run(AnalyzedDocumentType.ID_DOCUMENT, fields)
    rule = next(r for r in results if r["rule_id"] == "EXPIRY_AFTER_ISSUE")
    assert rule["status"] == "fail"


def test_rule_age_reasonable():
    fields = extract_fields(ID_TEXT, AnalyzedDocumentType.ID_DOCUMENT)
    results = RulesEngine().run(AnalyzedDocumentType.ID_DOCUMENT, fields)
    assert next(r for r in results if r["rule_id"] == "AGE_REASONABLE")["status"] == "pass"


# --- Scoring -----------------------------------------------------------------


def test_compute_score_is_weighted():
    score = compute_score(field_coverage=1.0, validation_rate=1.0, consistency_rate=1.0)
    assert score == 1.0
    score = compute_score(field_coverage=0.5, validation_rate=0.5, consistency_rate=0.5)
    assert score == 0.5
    score = compute_score(field_coverage=0.0, validation_rate=1.0, consistency_rate=1.0)
    assert score == 0.5


def test_compute_score_clamps():
    assert compute_score(field_coverage=2.0, validation_rate=2.0, consistency_rate=2.0) == 1.0
    assert compute_score(field_coverage=-1.0, validation_rate=0.0, consistency_rate=0.0) == 0.0


def test_status_derivation_branches():
    assert compute_verification_status(0.9, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.VERIFIED
    assert compute_verification_status(0.7, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.PARTIALLY_VERIFIED
    assert compute_verification_status(0.5, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.2, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.FAILED


def test_status_forced_to_needs_review():
    assert compute_verification_status(0.95, missing_critical_fields=True,
                                      critical_validation_failures=False,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.95, missing_critical_fields=False,
                                      critical_validation_failures=True,
                                      consistency_failures=False) is VerificationStatus.NEEDS_REVIEW
    assert compute_verification_status(0.95, missing_critical_fields=False,
                                      critical_validation_failures=False,
                                      consistency_failures=True) is VerificationStatus.NEEDS_REVIEW


def test_scoring_components_full_statement_verifies():
    document_type, fields, validations, consistency = _components(BANK_STATEMENT_TEXT)
    coverage, v_rate, c_rate, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert coverage == 1.0
    assert v_rate == 1.0
    assert c_rate == 1.0
    assert score == 1.0
    assert status is VerificationStatus.VERIFIED


def test_scoring_components_missing_critical_field():
    text = BANK_STATEMENT_TEXT.replace("Opening Balance: 1,250.50", "Opening Balance: -")
    document_type, fields, validations, consistency = _components(text)
    _, _, _, score, status = scoring_components(
        document_type,
        fields=fields,
        validation_results=validations,
        consistency_results=consistency,
    )
    assert score < 1.0
    assert status is VerificationStatus.NEEDS_REVIEW


def test_issues_are_human_readable():
    text = BANK_STATEMENT_TEXT.replace("Opening Balance: 1,250.50", "Opening Balance: -")
    document_type, _, validations, consistency = _components(text)
    issues = [
        v["message"] for v in validations if v["status"] != "valid"
    ] + [c["message"] for c in consistency if c["status"] != "pass"]
    assert any("Opening balance missing" in message for message in issues)


# --- Repository --------------------------------------------------------------


def _seed_application_and_document() -> tuple[int, int]:
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="repo-test")
        document = DocumentRepository(db).create(
            application_id=application.id,
            document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            original_filename="statement.pdf",
            stored_file_path="applications/APP-test/statement.pdf",
            file_type="application/pdf",
        )
        return application.id, document.id
    finally:
        db.close()


def _seed_amc_document_with_ocr() -> tuple[int, int]:
    db = SessionLocal()
    try:
        application = ApplicationRepository(db).create(created_by="repo-test")
        document = DocumentRepository(db).create(
            application_id=application.id,
            document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            original_filename="amc.pdf",
            stored_file_path="applications/APP-test/amc.pdf",
            file_type="application/pdf",
        )
        OCRRepository(db).create(
            document_id=document.id,
            raw_ocr_text=ACCOUNT_MAINTENANCE_CERTIFICATE_TEXT,
            ocr_engine="test",
        )
        return application.id, document.id
    finally:
        db.close()


def test_amc_document_is_routed_before_keyword_detection():
    # The AMC OCR text alone would keyword-detect as a generic category (see
    # test_checklist_field_labels_never_route_into_keyword_detection); the
    # service must trust the splitter's storage-level classification instead
    # and run the AMC extractor against it.
    application_id, document_id = _seed_amc_document_with_ocr()
    db = SessionLocal()
    try:
        response = DocumentAnalysisService(db).analyze(application_id=application_id)
        item = next(i for i in response.items if i.document_id == document_id)
        assert item.outcome is AnalysisOutcome.ANALYZED
        row = DocumentAnalysisRepository(db).get_by_document(document_id)
        assert (
            row.document_type
            == AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE.value
        )
        assert row.extracted_fields["account_holder"] == "KHYBER PROVINCE UTILITIES BOARD"
        assert row.extracted_fields["iban"] == "PK36FUTB0000001123456702"
    finally:
        db.close()


def test_repository_upsert_creates_then_updates():
    application_id, document_id = _seed_application_and_document()
    db = SessionLocal()
    try:
        repository = DocumentAnalysisRepository(db)
        first = repository.upsert(
            application_id=application_id,
            document_id=document_id,
            document_type=AnalyzedDocumentType.BANK_STATEMENT.value,
            extracted_fields={"account_number": "123"},
            validation_results=[{"field": "account_number", "status": "valid"}],
            consistency_results=[],
            confidence_score=0.7,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED.value,
            analysis_version="1.0.0",
            processing_time_ms=10,
        )
        assert repository.get_by_document(document_id) is first
        updated = repository.upsert(
            application_id=application_id,
            document_id=document_id,
            document_type=AnalyzedDocumentType.BANK_STATEMENT.value,
            extracted_fields={"account_number": "456", "iban": "DE..."},
            validation_results=[{"field": "account_number", "status": "valid"}],
            consistency_results=[],
            confidence_score=0.9,
            verification_status=VerificationStatus.VERIFIED.value,
            analysis_version="1.0.0",
            processing_time_ms=20,
        )
        assert updated.id == first.id
        results = repository.get_by_application(application_id)
        assert len(results) == 1
        assert results[0].extracted_fields == {"account_number": "456", "iban": "DE..."}
        assert results[0].confidence_score == 0.9
        assert results[0].verification_status == VerificationStatus.VERIFIED.value
    finally:
        db.close()
