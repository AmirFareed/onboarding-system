"""Deterministic field extraction from OCR text.

The analysis pipeline turns the raw text of a document into a normalized set of
structured fields. No machine learning is involved: every field is produced by a
regex pattern and a post-processing step, so results are reproducible and
explainable. The document type is inferred first (``detect_document_type``) and
selects the extractor whose patterns best fit the document's expected layout.
"""

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from app.document_analysis.constants import AnalyzedDocumentType
from app.document_analysis.exceptions import UnsupportedDocumentType
from app.document_processing.constants import PAGE_SEPARATOR


def _parse_amount(raw: str) -> float | None:
    """Parse a monetary string into a float.

    Handles thousands separators and decimal marks in both ``1,250.50`` and
    ``1.250,50`` conventions, as well as optional currency prefixes.

    Args:
        raw: Raw amount text (e.g. ``"1,250.50"``, ``"EUR 45,000.00"``).

    Returns:
        The amount as a float, or ``None`` when it cannot be parsed.
    """
    cleaned = raw.strip().replace(" ", "")
    cleaned = re.sub(r"^(?:EUR|USD|GBP|€|£|\$)", "", cleaned)
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) > 1 and len(parts[-1]) == 3 and all(
            1 <= len(part) <= 3 for part in parts[:-1]
        ):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return None if value != value or value in (float("inf"), float("-inf")) else value


def _parse_date(raw: str) -> date | None:
    """Parse a date string into a :class:`datetime.date`.

    Supports ISO (``YYYY-MM-DD``), slash (``DD/MM/YYYY``), hyphen
    (``DD-MM-YYYY``) and textual month (``DD Mon YYYY``, ``DD-Mon-YYYY``)
    representations, which cover the realistic OCR output of financial
    documents.

    Args:
        raw: Raw date text.

    Returns:
        The parsed date, or ``None`` when it cannot be parsed.
    """
    value = raw.strip()
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _as_iso_date(raw: str) -> str | None:
    """Parse a date and return it as an ISO ``YYYY-MM-DD`` string."""
    parsed = _parse_date(raw)
    return parsed.isoformat() if parsed is not None else None


def _as_iso_date_dotted(raw: str) -> str | None:
    """Parse a dot-separated ``DD.MM.YYYY`` date (the format printed on a real
    Pakistani CNIC) and return it as an ISO ``YYYY-MM-DD`` string.

    Deliberately separate from :func:`_as_iso_date`/:func:`_parse_date`: the
    real CNIC samples this was built against use dots, not the slash/ISO/
    textual-month formats those already handle, and adding dots there would
    change parsing behaviour for every other extractor that reuses them.
    """
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def _as_iso_date_day_of_month(raw: str) -> str | None:
    """Parse the real Bilateral Agreement template's execution-date clause
    ("this <DD> day of <MM>, <YYYY>") and return it as an ISO string.

    Deliberately separate from :func:`_as_iso_date`: confirmed against both
    real cached samples, this template states the day-of-month and month as
    two bare numbers in that order (not a month name), a shape none of the
    other date parsers handle. Returns ``None`` both when the numbers don't
    form a real date and -- just as importantly -- when the template's blanks
    were never filled in (confirmed real: one of the two samples leaves this
    clause entirely blank, "on this day of , 20__"), which never reaches this
    parser at all since the pattern requires the digits to be present.
    """
    match = re.match(r"(\d{1,2})\s+day\s+of\s+(\d{1,2}),\s*(\d{4})", raw.strip())
    if match is None:
        return None
    day, month, year = match.groups()
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _as_float(raw: str) -> float | None:
    """Parse an amount and return it as a float."""
    return _parse_amount(raw)


def _as_int(raw: str) -> int | None:
    """Parse the first integer found in a string."""
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def _as_statement_period(raw: str) -> dict[str, str] | None:
    """Parse ``<start> - <end>`` period text into a structured dict.

    Returns ``None`` unless both bounds parse, keeping the extracted value
    strictly typed for the consistency rules.
    """
    match = re.search(r"(.+?)\s*(?:-|—|to)\s*(.+)", raw, flags=re.IGNORECASE)
    if match is None:
        return None
    start = _parse_date(match.group(1))
    end = _parse_date(match.group(2))
    if start is None or end is None:
        return None
    return {"start": start.isoformat(), "end": end.isoformat()}


def _as_salary_month(raw: str) -> str | None:
    """Normalize a salary month into ``YYYY-MM``.

    Accepts ISO (``2026-01``), slash (``2026/01``) and ``January 2026`` forms.
    """
    iso = re.search(r"(\d{4})[-/](\d{1,2})", raw)
    if iso:
        year, month = iso.groups()
        return f"{year}-{int(month):02d}"
    textual = re.search(r"([A-Za-z]+)\s+(\d{4})", raw)
    if textual:
        try:
            month = datetime.strptime(textual.group(1), "%B").month
        except ValueError:
            try:
                month = datetime.strptime(textual.group(1), "%b").month
            except ValueError:
                return None
        return f"{textual.group(2)}-{month:02d}"
    return None


def _trim(raw: str) -> str:
    """Trim whitespace and trailing punctuation from a raw field value."""
    return raw.strip().strip(":;|").strip()


def _as_single_line(raw: str) -> str:
    """Collapse internal newlines/runs of whitespace into single spaces.

    Some real captures span an OCR line break (e.g. a name wrapped mid-value);
    the raw group otherwise keeps the literal newline.
    """
    return re.sub(r"\s+", " ", raw).strip()


#: Field labels the bank-account block parser understands, ordered most specific
#: first. Each entry maps a label pattern to the field key it feeds. Built
#: against the real cached layouts (Confidential Data/.ocr_cache/): the AMC
#: copies interleave label/value lines (same-line "Label: value", dotted-leader
#: "Label:... value", or bare label followed by its value on the next line,
#: sometimes wrapped over several lines); the Tripartite copy stacks a column
#: table (header block, then a value block mapped positionally). See
#: ``_extract_bank_account_block`` for the two scan passes.
_BANK_LABELS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"account\s*no\.?\s*/?\s*iban", re.IGNORECASE), "account_number"),
    (re.compile(r"iban\s*/?\s*account\s*no\.?", re.IGNORECASE), "account_number"),
    (re.compile(r"title\s*of\s*account", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*title", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*holder", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*name", re.IGNORECASE), "account_holder"),
    (re.compile(r"account\s*number", re.IGNORECASE), "account_number"),
    (re.compile(r"account\s*no\.?", re.IGNORECASE), "account_number"),
    (re.compile(r"(?:a/?c|ac)\s*no\.?", re.IGNORECASE), "account_number"),
    (re.compile(r"bank\s*name", re.IGNORECASE), "bank_name"),
    (re.compile(r"iban", re.IGNORECASE), "iban"),
)

#: Table row-index headers ("S#", "S.No", "Sr. No", ...). A column block with
#: this header carries a leading row number that must never be mistaken for an
#: account number value.
_ROW_INDEX_HEADER = re.compile(
    r"^(?:s\s*[/#.]?\s*no\.?|s\s*#|sr\.?\s*no\.?|s/?no\.?|#)\s*$", re.IGNORECASE
)

#: A parenthetical qualifier directly after a field label ("Account No. (T-24
#: System)") names the bank system/application the account is maintained
#: under -- it is not the value. Consumed into the label so the value that
#: follows (same line after a separator, or on the next line) is captured.
#: Only stripped when the parenthesis is the first token after the label, so a
#: real parenthetical value ("Account No.: (PK06...)") is never eaten.
_QUALIFIER_RE = re.compile(r"\s*\([^()]*\)")


def _match_label(line: str) -> tuple[str, str] | None:
    """Return ``(field_key, remainder)`` when ``line`` starts with a known
    bank-account field label, else ``None``.

    ``remainder`` is everything after the label (and any parenthetical system
    qualifier), before any value extraction. It may be empty for a bare label
    whose value is on the next line.
    """
    s = line.strip()
    if not s:
        return None
    for pattern, key in _BANK_LABELS:
        match = pattern.match(s)
        if match is not None:
            remainder = s[match.end():]
            qualifier = _QUALIFIER_RE.match(remainder)
            if qualifier is not None:
                remainder = remainder[qualifier.end():]
            return key, remainder
    return None


def _is_iban_like(value: str) -> bool:
    """Return True when ``value`` is a structurally valid IBAN (ignoring OCR
    line-break spaces)."""
    cleaned = re.sub(r"\s+", "", value)
    return bool(re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", cleaned))


def _is_value_like_line(line: str) -> bool:
    """Return True when a line reads as a standalone field value rather than
    prose or a label continuation.

    Used to stop wrapped multi-line value capture before the next field's
    label (e.g. a CNIC or date that follows an account title in a certificate).
    """
    s = line.strip()
    if not s or _match_label(s) is not None:
        return False
    if re.fullmatch(r"\d{4,}", s):
        return True
    if re.fullmatch(r"\d{5}-\d{7}-\d", s):
        return True
    if re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", s):
        return True
    if re.search(r"\b(?:PKR|USD|EUR|Rs\.?)\b", s, re.IGNORECASE):
        return True
    if re.search(r"\b[A-Z]{2}\d{2}[A-Z0-9]{8,}\b", s):
        return True
    return bool(re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", s))


def _looks_like_column_header(line: str) -> bool:
    """Return True when a line plausibly continues a column-header run (a
    short, non-numeric caption), i.e. it should be skipped as OCR noise between
    recognized headers rather than breaking the run or starting the value
    block."""
    s = line.strip()
    if not s or len(s) > 20:
        return False
    if s[0].isdigit() or s.startswith(("(", "[", "PK", "PN")):
        return False
    return not re.fullmatch(r"[\d.,]+", s)


def _normalize_account_holder(raw: str) -> str | None:
    """Clean a captured account-holder value, or return ``None`` when it is not
    a real account title (e.g. a captured field label, a bare number, a
    placeholder like "N/A", or a lone parenthetical system qualifier)."""
    value = _as_single_line(raw).strip().strip(".,:;|-").strip()
    if not value or _is_header(value) or value.isdigit():
        return None
    if re.fullmatch(r"\([^()]*\)", value):
        return None
    if value.lower() in {"n/a", "na", "nil", "none", "-", "--", "not applicable"}:
        return None
    return value


def _normalize_account_number(raw: str) -> tuple[str | None, str | None]:
    """Split a captured account-number value into ``(account_number, iban)``.

    Handles the real value shapes seen in the OCR cache: a bare account number
    (an all-digit value), a combined ``<number>/<IBAN>`` pair, an IBAN alone
    (the Tripartite account slot), and an account number with a parenthetical
    IBAN tail. An all-digit value of length <= 3 is a row index / page marker,
    never an account number.
    """
    value = raw.strip().rstrip(".:;-/ ").strip()
    iban_tail: str | None = None
    paren = re.search(r"\((.+)\)?\s*$", value)
    if paren is not None and paren.start() > 0:
        tail = paren.group(1).strip()
        head = value[: paren.start()].strip()
        if _is_iban_like(tail):
            iban_tail = re.sub(r"\s+", "", tail)
            value = head
    if "/" in value:
        left, right = (part.strip() for part in value.split("/", 1))
        if _is_iban_like(right):
            return left or None, re.sub(r"\s+", "", right)
        if _is_iban_like(left):
            return right or None, re.sub(r"\s+", "", left)
        if re.search(r"\d", value) and len(value) >= 4:
            return value, iban_tail
        return None, iban_tail
    if _is_iban_like(value):
        return None, re.sub(r"\s+", "", value)
    if value.isdigit():
        if len(value) <= 3:
            return None, iban_tail
        return value, iban_tail
    if (
        re.search(r"\d", value)
        and len(value) >= 4
        and re.fullmatch(r"[A-Za-z0-9\-/]+", value)
    ):
        return value, iban_tail
    # Prose-laden remainder (e.g. an OCR line "account number (1BAN) PK86...
    # titled as Tehsil General Account" whose qualifier was stripped and whose
    # trailing words are not part of the number): fall back to the first
    # long alphanumeric run as a last resort, and only when it is itself a
    # structurally valid token. Pure-text values with no such run normalize
    # to nothing and are rejected.
    run = re.search(r"[A-Za-z0-9]{8,}", value)
    if run is not None:
        token = run.group(0)
        if _is_iban_like(token):
            return None, token
        if token.isdigit() and len(token) > 3:
            return token, iban_tail
    return None, iban_tail


def _normalize_iban(raw: str) -> str | None:
    """Clean a captured IBAN value, or return ``None`` when it is not a valid
    IBAN shape."""
    value = re.sub(r"\s+", "", raw.strip().rstrip(".:;-/ ").strip())
    return value if _is_iban_like(value) else None


def _emit(key: str, raw: str) -> list[tuple[str, str]]:
    """Normalize one raw capture and return the normalized captures to record.

    ``_acc_no_fallback`` records an IBAN-only value captured under an
    account-number label; ``_extract_bank_account_block`` promotes it to
    ``account_number`` only when no plain account number was found anywhere in
    the document (the Tripartite column-table case, where the account slot
    holds an IBAN).
    """
    if key == "account_holder":
        value = _normalize_account_holder(raw)
        return [("account_holder", value)] if value else []
    if key == "account_number":
        account, iban = _normalize_account_number(raw)
        emits: list[tuple[str, str]] = []
        if account is not None:
            emits.append(("account_number", account))
        elif iban is not None:
            emits.append(("_acc_no_fallback", iban))
        if iban is not None:
            emits.append(("iban", iban))
        return emits
    if key == "iban":
        value = _normalize_iban(raw)
        return [("iban", value)] if value else []
    return []


def _is_header(line: str) -> bool:
    """Return True when a line is a recognized field label (bank-account label
    or a table row-index header)."""
    s = line.strip()
    return _match_label(s) is not None or bool(_ROW_INDEX_HEADER.match(s))


def _consume_value_lines(
    lines: list[str], start: int, cap: int
) -> tuple[list[str], int]:
    """Collect the value following a bare label line.

    ``lines[start]`` is the first line after the label. Stops at the next
    recognized label, and -- after the first line -- before a line that itself
    looks like a field value (the wrapped-title continuation must not absorb
    the next field's label). For multi-line values (``cap > 1``, i.e. account
    titles) it also stops when the accumulated text's parentheses balance out:
    a wrapped parenthetical title ("DG GDA (GALIYAT DEVELOPMENT" / "AUTHORITY)")
    is complete once its closing paren is consumed, so a trailing unrelated
    all-caps line ("DEVELOPMENT FUND") is not absorbed. Returns
    ``(parts, next_index)``.
    """
    parts: list[str] = []
    n = len(lines)
    j = start
    balance = 0
    while j < n and len(parts) < cap:
        line = lines[j].strip()
        if not line:
            j += 1
            continue
        if _match_label(line) is not None:
            break
        nxt = lines[j + 1].strip() if j + 1 < n else ""
        if len(parts) >= 1 and (_is_value_like_line(line) or _is_value_like_line(nxt)):
            break
        prev_balance = balance
        balance += line.count("(") - line.count(")")
        parts.append(line)
        j += 1
        if cap > 1 and prev_balance > 0 and balance == 0:
            break
    return parts, j


def _extract_column_block(
    lines: list[str],
) -> tuple[list[tuple[str, str, int]], int, int] | tuple[None, None, None]:
    """Detect a stacked column-block bank table (header block followed by a
    positionally-mapped value block) and return its normalized captures.

    Returns ``(captures, block_start, block_end)`` where ``captures`` is a list
    of ``(field_key, value, line_index)`` and ``[block_start, block_end)`` is
    the region to skip in the interleaved pass. Returns ``(None, None, None)``
    when no valid block exists.

    Header lines are matched against ``_BANK_LABELS``/``_ROW_INDEX_HEADER``;
    unrecognized short caption lines between them are treated as OCR noise and
    skipped (the real Tripartite sample has an ``IENT`` column between ``Bank
    Name`` and ``Account Title``). Values are mapped positionally by recognized
    header, so noise headers do not consume a value. The block is only accepted
    when its account-number slot normalizes to something real, so a shifted
    mapping (or a plain "label/value" pair misread as a table) is rejected
    rather than emitted as wrong data.
    """
    n = len(lines)
    for start in range(n):
        if not _is_header(lines[start]):
            continue
        header_keys: list[str] = []
        j = start
        while j < n and len(header_keys) < 6 and j - start < 10:
            line = lines[j].strip()
            if not line:
                j += 1
                continue
            matched = _match_label(line)
            if matched is not None:
                header_keys.append(matched[0])
                j += 1
                continue
            if _ROW_INDEX_HEADER.match(line):
                header_keys.append("_row_index")
                j += 1
                continue
            if _looks_like_column_header(line):
                j += 1
                continue
            break
        if len(header_keys) < 2:
            continue
        values: list[str] = []
        k = j
        while k < n and len(values) < len(header_keys):
            line = lines[k].strip()
            if line:
                values.append(line)
            k += 1
        if len(values) != len(header_keys):
            continue
        account_value = None
        for key, value in zip(header_keys, values, strict=False):
            if key == "account_number":
                account_value = value
        if account_value is None:
            continue
        account_norm, iban_norm = _normalize_account_number(account_value)
        if account_norm is None and iban_norm is None:
            continue
        # Every recognized value slot must normalize to something real. A
        # shifted mapping (e.g. a plain label/value layout whose value line
        # happens to look like a caption header, like the parenthetical-label
        # AMC "Account No. (T-24 System)") would otherwise land an all-digit
        # value in the account_holder slot and be accepted -- reject it so the
        # interleaved pass handles the layout correctly.
        for key, value in zip(header_keys, values, strict=False):
            if key in ("_row_index", "bank_name"):
                continue
            if not _emit(key, value):
                continue_block = True
                break
        else:
            continue_block = False
        if continue_block:
            continue
        captures: list[tuple[str, str, int]] = []
        for key, value in zip(header_keys, values, strict=False):
            if key in ("_row_index", "bank_name"):
                continue
            emits = _emit(key, value)
            for emit_key, emit_value in emits:
                captures.append((emit_key, emit_value, start))
        return captures, start, k
    return None, None, None


def _interleaved_scan(
    lines: list[str], skip_start: int | None, skip_end: int | None
) -> list[tuple[str, str, int]]:
    """Scan label/value-interleaved bank fields, skipping a detected
    column-block region.

    Handles the same-line form (``Label: value`` and dotted-leader ``Label:...
    value``, e.g. the ZTBL page of GDA copy2) and the bare-label-then-value
    form (e.g. the wrapped title in NBP copy3). An inline value that fails
    normalization falls through to the bare-label path so a qualifier-only
    remainder ("Account No. (T-24 System)") still captures the value on the
    following line instead of being silently dropped. First occurrence in
    document order wins per field, so a page-1 value is never overwritten by a
    page-2 one.
    """
    captures: list[tuple[str, str, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        if skip_start is not None and skip_start <= i < skip_end:
            i += 1
            continue
        line = lines[i]
        if not line:
            i += 1
            continue
        matched = _match_label(line)
        if matched is None:
            i += 1
            continue
        key, remainder = matched
        if key not in ("account_holder", "account_number", "iban"):
            i += 1
            continue
        raw = re.sub(r"^[:.\-*\s]+", "", remainder)
        if raw:
            inline = _emit(key, raw)
            if inline:
                for emit_key, emit_value in inline:
                    captures.append((emit_key, emit_value, i))
                i += 1
                continue
        parts, i = _consume_value_lines(
            lines, i + 1, cap=3 if key == "account_holder" else 1
        )
        raw = " ".join(parts)
        if not raw:
            continue
        for emit_key, emit_value in _emit(key, raw):
            captures.append((emit_key, emit_value, i - 1))
    return captures


def _extract_bank_account_block(text: str) -> dict[str, str]:
    """Extract the bank-account block (account_holder, account_number, iban)
    from OCR text using the two structural layouts seen in the real cache:
    a stacked column table and interleaved label/value lines.

    Every value is normalized and shape-guarded -- a captured string that is a
    known field label, an all-digit row index of length <= 3, or any value that
    normalizes to nothing is rejected rather than emitted. Account number takes
    the first plain-number capture in document order; an IBAN-only capture
    under an account-number label is promoted to account_number only when no
    plain number exists anywhere in the document. When no labeled account
    holder exists, a sentence-level fallback
    (:func:`_extract_holder_from_sentence`) recovers the holder from prose
    ("the account of ..."), which is how the real DG_Sports AMC layout states
    it.
    """
    lines = [line.strip() for line in text.splitlines()]
    column_captures, block_start, block_end = _extract_column_block(lines)
    if column_captures is None:
        column_captures = []
    interleaved_captures = _interleaved_scan(lines, block_start, block_end)
    per_field: dict[str, tuple[str, int]] = {}
    for key, value, index in column_captures + interleaved_captures:
        if key == "_acc_no_fallback":
            continue
        if key not in per_field or index < per_field[key][1]:
            per_field[key] = (value, index)
    if "account_number" not in per_field:
        best: tuple[str, int] | None = None
        for key, value, index in column_captures + interleaved_captures:
            if key == "_acc_no_fallback" and (best is None or index < best[1]):
                best = (value, index)
        if best is not None:
            per_field["account_number"] = best
    if "account_holder" not in per_field:
        holder = _extract_holder_from_sentence(text)
        if holder is not None:
            per_field["account_holder"] = (holder, -1)
    return {
        key: per_field[key][0]
        for key in ("account_holder", "account_number", "iban")
        if key in per_field
    }


#: Sentence-level account-holder fallbacks for certificates that state the
#: holder in prose ("the account of ...", "account titled '...'") rather than
#: as its own labeled field -- the real DG_Sports AMC layout. Each pattern
#: anchors the capture on an account-ownership keyword so arbitrary prose
#: lines are never picked up. The value must start with an uppercase letter or
#: digit and is passed through the same guards as labeled captures.
#:
#: The three unquoted-capture patterns below end their capture group with
#: nothing else required in the regex after it -- no fixed trailing anchor
#: like pattern 5 below has -- so the stop condition has to come from the
#: capture itself. Confirmed real bug 2026-08-26 (see CONTEXT.md): the
#: original class, `[A-Z0-9 ,.&'()\-/]`, was uppercase-only, so on real
#: mixed-case text (e.g. "on behalf of TMA Thall.") the greedy quantifier
#: stopped dead at the first lowercase letter -- "TMA T", not "TMA Thall" --
#: a garbage truncation, not an honest miss.
#:
#: The obvious fix (just add lowercase letters) is unsafe on its own: tried
#: first, verified against every real AMC/Tripartite/Bilateral sample this
#: fallback can reach (all three extractors call it via
#: _extract_bank_account_block) plus this file's own hand-written AMC
#: fixtures, and it broke a real, previously-passing case --
#: PARALLEL_GENERATIONS_TEXT below (mirroring real DG_Sports AMC content:
#: "the account of SAMPLE SPORTS AUTHORITY maintained with this branch is
#: in good standing.") -- because a plain lowercase-inclusive greedy match
#: runs straight through the org name into "maintained with this branch is
#: in good standing", which the sentence-fallback's own bank/branch guard
#: then rejects outright as a bank-naming capture, losing the field
#: entirely. Excluding `.` from the class and stopping there (the fix
#: tried second) is *also* unsafe alone: it fixes the Tripartite case
#: (which ends right at a period: "...on behalf of TMA Thall.") but that
#: sentence has no period anywhere near the org name at all -- confirmed
#: real samples genuinely disagree on where the boundary sits.
#:
#: The two real shapes do agree on one thing: in this document corpus, a
#: real org/party name is written as a run of Title-Case-or-ALL-CAPS words
#: (each word starting with an uppercase letter -- "TMA Thall", "SAMPLE
#: SPORTS AUTHORITY"), and the prose that resumes after it always starts
#: with a lowercase word ("maintained", "wish", "hereby", ...) or the
#: sentence simply ends. So the capture group now stays non-greedy
#: (`{3,60}?`, was greedy `{3,60}`) with lowercase letters allowed in the
#: class (so a single stray-lowercase OCR misread *inside* a word, as in
#: the Tripartite fix, doesn't block the match), plus a required lookahead,
#: `(?=\.|\s+[a-z]|$)`, stopping the match at whichever comes first: a
#: literal period, whitespace immediately followed by a lowercase word (a
#: genuine word boundary into unrelated prose -- a stray lowercase letter
#: *inside* a word never triggers this, since there's no whitespace right
#: before it), or the end of the (flowed) text. Verified against both real
#: shapes above plus every real cached AMC/Tripartite/Bilateral sample and
#: every hand-written fixture in this file that reaches this fallback:
#: correct on both, zero regressions. The Bilateral real samples' separate
#: false-positive ("Party B" from an unrelated "revenue collected on behalf
#: of Party B" clause, which also legitimately ends at a period) is not
#: fixed by this boundary logic at all -- it's a different problem (the
#: wrong sentence matched, not a truncated one) -- see
#: `_GENERIC_PARTY_LABEL` below for that fix.
#:
#: One earlier, incorrect assumption corrected here: a prior session's
#: finding characterized the Tripartite bug's *correct* value as "TEHSIL
#: GENERAL ACCOUNT TMA THALL". Tracing which pattern and match actually
#: produces the captured value (not assuming) shows that text is a
#: *different*, unrelated real sentence ("...titled as TEHSIL GENERAL
#: ACCOUNT TMA THALL") that none of these patterns anchor on at all (no
#: literal "account titled"/"in the name of"/etc. immediately precedes it)
#: -- the actual matched sentence is "...on behalf of TMA Thall.", so the
#: correct, complete, non-truncated capture is "TMA Thall". Redesigning
#: which sentence this fallback should prefer is a separate, unrelated
#: scope question, not part of this truncation-boundary fix.
_HOLDER_SENTENCE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(
        r"account\s+titled?\s+(?:as\s+)?[\"'“]([^\"'”]{3,60})[\"'”]",
        re.IGNORECASE,
    ),
    re.compile(
        r"account\s+titled?\s+(?:as\s+)?"
        r"(?-i:([A-Z0-9][A-Za-z0-9 ,&'()\-/]{3,60}?)(?=\.|\s+[a-z]|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:in\s+the\s+name\s+of|in\s+name\s+of|on\s+behalf\s+of)\s+"
        r"(?:the\s+)?(?-i:([A-Z0-9][A-Za-z0-9 ,&'()\-/]{3,60}?)(?=\.|\s+[a-z]|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"account\s+(?:of|held\s+in\s+the\s+name\s+of|maintained\s+by|"
        r"belonging\s+to)\s+(?:the\s+)?"
        r"(?-i:([A-Z0-9][A-Za-z0-9 ,&'()\-/]{3,60}?)(?=\.|\s+[a-z]|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"certif\w*\s+that\s+"
        r"(?-i:([A-Z0-9][A-Za-z0-9 ,.&'()\-/]{3,60}?))\s+"
        r"(?:is\s+)?maintaining\s+(?:a|an|the)?\s*[^.!?\n]{0,40}\baccount\b",
        re.IGNORECASE,
    ),
)


#: Generic Party-A/Party-B-style defined-term placeholders, not real
#: organization names -- confirmed real and already-documented in this
#: codebase (BilateralAgreementExtractor's own class docstring: real
#: templates define "...hereinafter referred as First party or Party A or
#: Party 1" and "...hereinafter referred to as 'Client' or Second Party or
#: Party B or Party 2"; CLAUDE.md separately documents these same generic
#: labels appearing on every stamp paper regardless of document type).
#: Added 2026-08-26 after widening _HOLDER_SENTENCE_PATTERNS' character
#: class surfaced a real false-positive: on all 3 real Bilateral samples,
#: "on behalf of" now also matches an unrelated real sentence ("...revenue
#: collected on behalf of Party B[.] 6.4. If Party B wish to change...")
#: that has nothing to do with account titling, previously matched only by
#: accident of the old class blocking every "Party " capture outright.
#: Anchored at the start of the (already-trimmed) value so a real org name
#: that merely mentions a party term later is never rejected -- only a
#: capture that *is* one of these placeholders, optionally with trailing
#: OCR/section-number noise (e.g. "Party B 6" from "Party B 6.4."), is
#: excluded.
_GENERIC_PARTY_LABEL = re.compile(
    r"^(?:first|second)\s+party\b|^party\s*[ab12]\b|^client$",
    re.IGNORECASE,
)


def _extract_holder_from_sentence(text: str) -> str | None:
    """Return the account holder stated in a sentence, or ``None``.

    Fallback used only when no labeled account-holder field exists in the
    document. Runs against the text with line breaks flowed into spaces so a
    wrapped sentence is read as one. The captured value must survive the
    account-holder normalization guards and be at least 3 characters long.
    Captures naming a bank/branch (the subject of "maintaining an account" is
    the holder, never the bank) are rejected here -- this guard is restricted
    to the sentence-derived path so labeled account titles are unaffected.
    Captures that are just a generic Party-A/Party-B-style defined-term
    placeholder (see ``_GENERIC_PARTY_LABEL``) are rejected the same way.
    """
    flowed = re.sub(r"\s*\n\s*", " ", text)
    for pattern in _HOLDER_SENTENCE_PATTERNS:
        for match in pattern.finditer(flowed):
            value = _normalize_account_holder(match.group(1))
            if value is None or len(value) < 3:
                continue
            if re.search(r"\b(?:bank|branch)\b", value, re.IGNORECASE):
                continue
            if _GENERIC_PARTY_LABEL.match(value):
                continue
            return value
    return None


class RegexExtractor:
    """Extractor driven by a declarative map of field patterns.

    Subclasses declare the analysed document type, the regex for every field and
    an optional post-processor that converts the raw match into the normalized
    value. Fields that do not match are omitted from the result so downstream
    scoring can count them as missing.
    """

    document_type: AnalyzedDocumentType
    _patterns: dict[str, re.Pattern]
    _post: dict[str, Callable[[str], Any]] = {}

    def extract(self, text: str) -> dict[str, Any]:
        """Return the normalized fields extracted from ``text``.

        Args:
            text: Raw OCR text of the document.

        Returns:
            A dict mapping field name to its normalized value.
        """
        fields: dict[str, Any] = {}
        for name, pattern in self._patterns.items():
            match = pattern.search(text)
            if match is None:
                continue
            value = _trim(match.group(1))
            if not value:
                continue
            post = self._post.get(name)
            fields[name] = post(value) if post is not None else value
        return fields


class BankStatementExtractor(RegexExtractor):
    """Extracts structured fields from a bank statement."""

    document_type = AnalyzedDocumentType.BANK_STATEMENT

    _patterns = {
        "account_holder": re.compile(
            r"(?:Account Holder|Account Name)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_number": re.compile(
            r"(?:Account Number|A/?C No\.?|Account No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/ ]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "iban": re.compile(
            r"\bIBAN\b\s*[:|-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})",
            re.IGNORECASE,
        ),
        "bank_name": re.compile(
            r"(?:Bank Name|Bank)\s*[:|-]?\s*(?!Statement\b)(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "statement_period": re.compile(
            r"(?:Statement Period|Period|For the period)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "opening_balance": re.compile(
            r"(?:Opening Balance|Opening)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "closing_balance": re.compile(
            r"(?:Closing Balance|Closing)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "total_credits": re.compile(
            r"(?:Total Credits|Total In|Credits)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "total_debits": re.compile(
            r"(?:Total Debits|Total Out|Debits)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "currency": re.compile(
            r"(?:Currency|CCY)\s*[:|-]?\s*([A-Z]{3})",
            re.IGNORECASE | re.MULTILINE,
        ),
        "transaction_count": re.compile(
            r"(?:Transactions|No\.? of Transactions)\s*[:|-]?\s*(\d+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "opening_balance": _as_float,
        "closing_balance": _as_float,
        "total_credits": _as_float,
        "total_debits": _as_float,
        "statement_period": _as_statement_period,
        "transaction_count": _as_int,
    }


class PayslipExtractor(RegexExtractor):
    """Extracts structured fields from a salary slip / payslip."""

    document_type = AnalyzedDocumentType.PAYSLIP

    _patterns = {
        "employee_name": re.compile(
            r"(?:Employee Name|Name of Employee)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "employee_id": re.compile(
            r"(?:Employee ID|Emp\.? ID|Staff No\.?|Personnel No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "employer_name": re.compile(
            r"(?:Employer Name|Employer|Company)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "gross_salary": re.compile(
            r"(?:Gross Salary|Gross Pay|Gross)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "net_salary": re.compile(
            r"(?:Net Salary|Net Pay|Net)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "salary_month": re.compile(
            r"(?:Salary Month|Pay Period|Month)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "payment_date": re.compile(
            r"(?:Payment Date|Pay Date|Date Paid)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "gross_salary": _as_float,
        "net_salary": _as_float,
        "salary_month": _as_salary_month,
        "payment_date": _as_iso_date,
    }


class IdentityExtractor(RegexExtractor):
    """Extracts basic identity fields from a national ID or passport."""

    document_type = AnalyzedDocumentType.ID_DOCUMENT

    _patterns = {
        "full_name": re.compile(
            r"(?:Full Name|Name)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "date_of_birth": re.compile(
            r"(?:Date of Birth|DOB|Birth Date)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "document_number": re.compile(
            r"(?:ID Number|Document Number|National ID No\.?|Passport No\.?)\s*[:|-]?\s*([A-Za-z0-9\-]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "nationality": re.compile(
            r"(?:Nationality|Nationality Code)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "issue_date": re.compile(
            r"(?:Issue Date|Date of Issue)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "expiry_date": re.compile(
            r"(?:Expiry Date|Date of Expiry|Valid Until|Expires)\s*[:|-]?\s*([A-Za-z0-9\-/.]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "date_of_birth": _as_iso_date,
        "issue_date": _as_iso_date,
        "expiry_date": _as_iso_date,
    }


class TaxExtractor(RegexExtractor):
    """Extracts basic fields from a tax document."""

    document_type = AnalyzedDocumentType.TAX_DOCUMENT

    _patterns = {
        "taxpayer_name": re.compile(
            r"(?:Taxpayer Name|Taxpayer's Name|Taxpayer)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "tax_reference_number": re.compile(
            r"(?:Tax Reference Number|Tax Reference|UTR|Tax ID)\s*[:|-]?\s*([A-Za-z0-9\-]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "tax_year": re.compile(
            r"(?:Tax Year|Assessment Year|Year)\s*[:|-]?\s*((?:19|20)\d{2})",
            re.IGNORECASE | re.MULTILINE,
        ),
        "gross_income": re.compile(
            r"(?:Gross Income|Total Income|Adjusted Gross Income)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "total_tax": re.compile(
            r"(?:Total Tax|Tax Due|Income Tax|Tax Payable)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "currency": re.compile(
            r"(?:Currency|CCY)\s*[:|-]?\s*([A-Z]{3})",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "tax_year": _as_int,
        "gross_income": _as_float,
        "total_tax": _as_float,
    }


#: Platform names docs/Master_Rules_Combined.md requires the agreement to
#: name explicitly (Section 7, "Platform Terminology"). Matched literally
#: rather than via a labeled regex since the term appears embedded in prose,
#: not after a "Field:" label. "Paymir" added 2026-08-22: confirmed real --
#: both real cached samples define it verbatim ("'PAYMIR' means Digital
#: Payment Gateway developed by the KPITB") and use it throughout; neither
#: of the other three spec-guessed names appears in either real sample at
#: all. Not a rename of an existing entry -- a fourth, real, previously
#: unvalidated name; the other three are left in place since no real sample
#: has yet confirmed or ruled them out.
_KNOWN_PLATFORM_NAMES: tuple[str, ...] = ("Digital Muhasil", "PayMin", "Paymere BCX", "Paymir")


def _as_platform_name(raw: str) -> str | None:
    """Return whichever known platform name is present in ``raw``, if any."""
    for name in _KNOWN_PLATFORM_NAMES:
        if name.lower() in raw.lower():
            return name
    return None


#: Regex matching the real production page separator (``PAGE_SEPARATOR`` in
#: ``app.document_processing.constants``, e.g. ``"\n\n--- Page 5 ---\n\n"``),
#: derived from the actual constant rather than a second hardcoded literal so
#: the two can never silently drift apart. Built by splitting the format
#: string on its one placeholder and re-escaping each literal half around a
#: ``\d+`` for the real page number.
_page_separator_prefix, _page_separator_suffix = PAGE_SEPARATOR.split("{page_index}")
_PAGE_SEPARATOR_PATTERN: str = (
    re.escape(_page_separator_prefix) + r"\d+" + re.escape(_page_separator_suffix)
)

#: The CamScanner app's own watermark, stamped at the bottom of every single
#: scanned page immediately before the page boundary -- confirmed 2026-08-26
#: across all 3 real Bilateral samples on file (Confidential Data/.ocr_cache/
#: Conservator_Wildlife_Peshawar_Zoo, schdule_of_charges_or_bilateral,
#: combined_kp_ppra_test/doc 42978), dozens of occurrences total, always the
#: identical two-line "CS"/"CamScanner" shape right before every page's
#: separator, never just before some pages -- a scanning-app artifact of
#: every page in these documents, not something specific to the fee-table
#: page. Deliberately a post-extraction cleanup, not part of the
#: transaction_charges stop-boundary regex above: the page-separator match is
#: the authoritative, structurally-grounded boundary; this only trims the
#: cosmetic watermark line pair that boundary leaves attached to the end of
#: the real captured content.
_TRAILING_SCANNER_WATERMARK_RE = re.compile(r"\n\s*CS\s*\n\s*CamScanner\s*$", re.IGNORECASE)


def _strip_trailing_scanner_watermark(raw: str) -> str:
    """Strip a trailing CamScanner app watermark line pair from a captured
    multi-line field value, if present."""
    return _TRAILING_SCANNER_WATERMARK_RE.sub("", raw).rstrip()


class BilateralAgreementExtractor(RegexExtractor):
    """Extracts structured fields from a Bilateral Agreement (SLA).

    Real-sample validated 2026-08-22 against the first two real samples ever
    found for this type (Conservator Wildlife Peshawar Zoo and a second,
    independent department -- both "AGREEMENT FOR DIGITAL PAYMENT COLLECTION
    VIA PAYMIR" between KPITB and a real department, same template). The
    original patterns below were written blind against
    docs/Master_Rules_Combined.md Section 7 and, run against these two real
    samples, scored 6 of 7 fields missing and the 7th (``account_number``) as
    garbage -- a table row index ("01"), the same failure class already fixed
    for AMC/Tripartite. Every field below was rewritten from what these two
    real, cross-validated samples actually contain, not the spec:

    organization_name previously required a labeled "Department:"/
    "Organization Name:" field that does not exist anywhere in either real
    sample. The real party-B name appears in prose, at the start of the
    paragraph that follows the "...Party A;\\nand\\n" transition between the
    two parties' definition paragraphs (confirmed identical boilerplate in
    both samples) -- anchored on that fixed-width transition instead.

    platform_name's three spec-guessed names (Digital Muhasil/PayMin/Paymere
    BCX) appear in neither real sample; both instead define and use "PAYMIR"
    throughout ("'PAYMIR' means Digital Payment Gateway developed by the
    KPITB"). Added as a fourth known name -- the other three are left in
    place since no real sample has confirmed or ruled them out yet.

    transaction_charges was anchored on the literal string "Section 5.2",
    which never appears -- the real numbering is bare "5.2." (no "Section"
    prefix). The real content under it is also not a single line but a full
    tiered PKR fee table (7 tiers, confirmed byte-identical boilerplate
    across both real samples), so the capture now runs from the "5.2."
    heading to the start of the next top-level numbered section ("6.
    DEPOSIT & DISBURSEMENT...") rather than one line -- bounded by the
    document's own real section structure, not a magic line count, and kept
    as a multi-line value (like BusinessRequirementDocumentExtractor's
    revenue_services_listed) since this is a human-review context field, not
    a field anything else parses further.

    account_holder/account_number/iban previously used the same label-
    anchored same-line regexes already documented as producing the row-index
    ("01") garbage-capture bug for AMC/Tripartite before their fix. Both real
    samples have the identical stacked "Sr No / Bank Name / Account No"
    column-table shape that fix's shared structural parser
    (``_extract_bank_account_block``) already recognizes and handles
    correctly out of the box -- reused via an ``extract()`` override below,
    the same convention TripartiteAgreementExtractor already uses. Neither
    real sample's table has an "Account Title"/"Account Holder" column at
    all (only Bank Name + Account No), so account_holder is an honest,
    structural miss for this document type -- not force-mapped from the bank
    name, which would be a different, wrong value. The regex patterns are
    kept as-is for layouts the structural parser doesn't recognize, matching
    the same fallback convention.

    effective_date's real clause ("...made and entered into on this <DD> day
    of <MM>, <YYYY>...") states the day-of-month and month as two bare
    numbers, not the "DD Month YYYY"/slash/ISO shapes the shared date parsers
    handle -- a dedicated parser (``_as_iso_date_day_of_month``) was added.
    One of the two real samples leaves this clause's blanks entirely unfilled
    ("on this day of , 20__") -- confirmed to honestly miss rather than guess,
    since the pattern requires the digits to be present at all.

    **Verified after, against both real samples**: organization_name,
    platform_name, transaction_charges, account_number and iban now extract
    correctly on both; effective_date extracts correctly on the one sample
    that states it and honestly misses on the one that doesn't;
    account_holder honestly misses on both (matches the real table shape, not
    a regression). See CONTEXT.md for the full field-by-field before/after.
    """

    document_type = AnalyzedDocumentType.BILATERAL_AGREEMENT

    _patterns = {
        "organization_name": re.compile(
            # Fixed-width lookbehind on the parties' paragraph-transition
            # boilerplate ("...Party A;\nand\n"), confirmed identical in both
            # real samples; captures up to the first comma or "(" so a
            # trailing "(KP-PSRA)"-style abbreviation is left for a human to
            # read in context rather than swallowed into the value.
            r"(?<=;\nand\n)([^,\n(]+)",
        ),
        "platform_name": re.compile(
            r"(Digital Muhasil|PayMin|Paymere BCX|Paymir)",
            re.IGNORECASE,
        ),
        "transaction_charges": re.compile(
            # Three stop conditions, either one ending the capture:
            # (1) an ALL-CAPS section-header line ("6. DEPOSIT & DISBURSEMENT
            # OF FUNDS"), not just any numbered line -- a bare \d+\. boundary
            # latches onto the sentence-case "1. Open your mobile camera..."
            # how-to-verify list on an e-stamp verification page one real
            # sample inserts before its own "6." section.
            # (2)/(3) a page-boundary marker -- both real samples insert a
            # second e-stamp/STAMPING cover page mid-section, between the fee
            # table and "6.", so the header alone still swallows that whole
            # intervening page as noise (confirmed live, application 20322
            # document 42978, 2026-08-26 -- see CONTEXT.md). Two different
            # marker forms are matched because two different real text
            # sources use two different ones: _PAGE_SEPARATOR_PATTERN is the
            # real production separator (app.document_processing.constants
            # .PAGE_SEPARATOR, e.g. "\n\n--- Page 5 ---\n\n") that
            # DocumentAnalysisService.analyze() actually receives; the
            # literal "--- page break ---" is a *different*, cache-tool-only
            # marker (backend/scripts/ocr_cache.py's own page join, never
            # written by production code) that the two originally-validated
            # Confidential Data/.ocr_cache/ samples happen to be stored with.
            # Originally this pattern only had the cache-tool marker, which
            # made both cached fixtures pass while silently never matching
            # any real document.raw_ocr_text a live pipeline run actually
            # produces -- the exact class of mistake this project's own
            # CrossBranchCodeRule/CrossPeriodRule history warns about, just
            # inverted: validated against a fixture artifact instead of a
            # too-thin real sample. Kept both markers rather than swapping
            # one for the other so neither validation path regresses.
            r"5\.2\.?\s*Transaction Charges:?\s*\n(.*?)"
            r"(?=\n\d+\.\s+(?-i:[A-Z][A-Z\s&,]*)\n|\n--- page break ---\n|"
            + _PAGE_SEPARATOR_PATTERN
            + r")",
            re.IGNORECASE | re.DOTALL,
        ),
        "account_holder": re.compile(
            r"(?:Account Title|Account Holder|Account Name)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_number": re.compile(
            r"(?:Account Number|A/?C No\.?|Account No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/ ]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "iban": re.compile(
            r"\bIBAN\b\s*[:|-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})",
            re.IGNORECASE,
        ),
        "effective_date": re.compile(
            r"on\s+this\s+(\d{1,2}\s+day\s+of\s+\d{1,2},\s*\d{4})",
            re.IGNORECASE,
        ),
    }

    _post = {
        "platform_name": _as_platform_name,
        "transaction_charges": _strip_trailing_scanner_watermark,
        "effective_date": _as_iso_date_day_of_month,
    }

    def extract(self, text: str) -> dict[str, Any]:
        # Structural parser takes precedence for account_holder/account_number
        # /iban -- see the class docstring. Regex patterns above remain as the
        # fallback for layouts the structural parser doesn't recognize.
        fields = super().extract(text)
        block = _extract_bank_account_block(text)
        for key in ("account_holder", "account_number", "iban"):
            if key in block:
                fields[key] = block[key]
        return fields


class AuthorityLetterExtractor(RegexExtractor):
    """Extracts structured fields from an Authority Letter.

    Real Authority Letters follow a standard prose template -- confirmed
    against three independent real departments in Confidential Data/:
    "It is hereby authorized that Mr. <name>, <designation> is authorized to
    deal with and conduct correspondence and matter(s) related to 1-Link and
    the Khyber Pakhtunkhwa Information Technology Board (KPITB) on (the)
    behalf of <organization>." Only this prose-embedded variant is
    validated. docs/IMPLEMENTATION_ROADMAP.md also describes a labeled-block
    variant ("Name:"/"Designation:" fields) that has not yet turned up in a
    real sample -- not built blind (see the roadmap's Phase 1 "why this
    can't be done blind" note); a document using that form will simply
    extract nothing here rather than guess.

    focal_person_name's stopping point is deliberately not limited to a
    comma or paren: a third real department (confirmed 2026-08-18, TMA Lal
    Dir Upper) phrases the sentence as "It is here by submitted that Mr.
    <name> CNIC# <number>... is authorized..." -- no designation clause at
    all, so neither delimiter ever appears. The pattern now also stops at a
    following "CNIC" or "is authorized", whichever comes first, without
    changing what it captures on the original two departments (both still
    hit their own comma/paren first). focal_person_designation is
    deliberately NOT loosened to match -- that department's real letter
    genuinely never states a designation, so it correctly keeps missing
    that field rather than guessing one from nearby text.

    Two bugs fixed 2026-08-19 (department decision, see CONTEXT.md), both
    tested directly against GDA Abbotabad's real cached text:

    focal_person_name/focal_person_designation previously matched only the
    literal "Mr" prefix; GDA Abbotabad's real letter uses "Dr." ("It is
    hereby authorized that Dr. Samar Hayat Khan..."), which never matched
    at all. Generalized to a small, evidence-grounded honorific set --
    Mr/Mrs/Ms/Dr, the only two actually seen across 4 real samples -- not
    an attempt to anticipate every possible honorific. Separately, GDA's
    designation ("Taxation Officer-I") sits on the line *after* the name,
    unlike the other 3 samples' same-line "Mr. <name>, <designation>"
    shape; both patterns' stopping lookahead now tolerates crossing exactly
    one newline before finding the comma, tested against all 4 real
    samples to confirm this doesn't change what the other 3 already
    correctly capture.

    organization_name previously captured "this" from GDA's real sentence
    ("...on behalf of this\nAuthority.") -- a genuine garbage capture, not
    an honest miss, since "this" doesn't identify the organization at all.
    The letter refers back to itself by pronoun instead of naming the org
    in this clause, unlike the other 3 real samples. Fixed via extract()
    below: when the primary pattern's capture is a generic backward
    reference ("this"/"the said"/"said", optionally followed by "authority"
    /"board"/"office"/"department"), fall back to the letterhead -- the
    first substantive line before the "AUTHORITY LETTER" title, skipping
    contact-info lines -- which correctly names the organization in all 4
    real samples. Scoped narrowly to the exact backward-reference shape
    confirmed real, not a general letterhead parser: the other 3 samples'
    letterheads vary too much in format to parse generically, and their
    primary "on behalf of X" capture already works, so they never reach
    this fallback at all.

    Two more real samples (confirmed 2026-08-20: TMA Lal Qilla Dir Lower,
    TMA Samarbagh Dir Lower) phrase the same backward reference as "on
    behalf of the\nAuthority." -- bare "the", not "this"/"the said", and
    wrapped onto a second line. The capture group previously stopped at
    the line break (matching only "the"), which isn't in
    _GENERIC_ORG_REFERENCE's alternation, so it fell through as a literal
    "the" garbage value instead of ever reaching the fallback. Fixed by
    (a) letting the capture cross exactly one more newline, the same
    one-newline tolerance focal_person_name/designation already use, and
    (b) adding bare "the" to _GENERIC_ORG_REFERENCE's alternation --
    anchored on both ends, so it only matches when the entire normalized
    capture is "the" plus, optionally, one of the four backward-reference
    nouns, never a real org name that merely starts with "the". Confirmed
    against all 8 real samples this doesn't change the 6 that already
    extracted correctly (GDA Abbotabad's "this\nAuthority" now crosses the
    same extra newline too, but "this Authority" still matches the
    backward-reference check exactly as bare "this" did, so it still
    resolves through the same fallback to the same letterhead value).

    Unlike docs/Master_Rules_Combined.md Section 2 ("account maintenance
    details must appear at the top"), none of the four real samples
    reviewed carries any bank account information on the Authority Letter's
    own page -- account_holder/account_number/iban are extracted
    opportunistically (reusing the same patterns as
    BilateralAgreementExtractor) but are not critical fields, see
    constants.CRITICAL_FIELDS. Some samples do incidentally populate
    account_number from an absorbed, structurally separate Account-
    Maintenance-Certificate-looking page that lands in the same document
    group (a known, unfixed splitter absorption gap) -- opportunistic by
    design, so this doesn't threaten the critical fields' validated status.

    Three more real bugs fixed 2026-08-26 (surfaced incidentally during an
    unrelated organization-name cross-document consistency investigation --
    see CONTEXT.md):

    DG Sports's real "on the behalf of Directorate." states no demonstrative
    at all, just the bare generic noun "Directorate" -- the same underlying
    phenomenon as "this Authority"/"the Authority" (a self-referential
    shorthand instead of the real name), different surface form, so
    "directorate" was added to _GENERIC_ORG_REFERENCE as a standalone
    alternative. Its letterhead's first substantive line is an unrelated
    slogan ("Sports are essential for the development of a happy, healthy &
    vigorous society"), which the original positional fallback would have
    wrongly picked -- fixed by preferring, when the generic reference
    supplies a specific word to search for (see _anchor_word_for), the first
    letterhead line that actually contains it ("DIRECTORATE GENERAL OF
    SPORTS") over blind positional order.

    TMA Lal Qilla Dir Lower and TMA Samarbagh Dir Lower both reach the
    existing "the\nAuthority" fallback correctly, but their letterheads open
    with a job-title heading line ("OFFICE OF THE TEHSIL MUNICIPAL
    OFFICE(R)") before the real organization name -- the fallback was
    picking that heading instead. Confirmed this is a job title, not the
    organization's own name, by checking the CONFIRMED real ONE_LINK_LETTER
    sibling values for both departments, which independently state the full
    real name ("TEHSIL MUNICIPAL ADMINISTRATION, LAL QILA" / "...
    SAMARBAGH"). Fixed by skipping the confirmed real job-title heading
    shape (_OFFICE_TITLE_HEADER) and, since the real name genuinely spans
    two letterhead lines here ("TEHSIL MUNICIPAL ADMINISTRATION" then a
    place-name line), joining the next substantive line whenever the
    candidate ends in "Administration" -- confirmed structurally consistent
    across every real TMA sample checked, not just these two (e.g. TMA
    Thall Hangu's own letterhead and TMA Khal Dir Lower's own account-detail
    block both independently show the identical "...ADMINISTRATION
    <place>" two-line shape). Verified this doesn't touch GDA Abbotabad's
    already-correct single-line fallback value, which never ends in
    "Administration".

    TMA Lal Dir Upper's real "on behalf of Tehsil Municipal Administration
    Dir please." is a different, still-open problem: not a regex boundary
    bug -- the pattern faithfully captures this real OCR'd sentence's entire
    content up to its period -- but a genuine OCR misread. The letterhead
    ("TEHSIL MUNICIPAL ADMINISTRATION LAL DIR UPPER") and the letter's own
    signature block ("TEHSIL-MUCNICIPAL ADMINISTRATION\nDIR UPPER") both
    independently confirm the real suffix is "DIR UPPER", not "please" --
    but no safe, generalizable pattern exists to detect and strip one
    corrupted trailing word from an otherwise-correct capture without
    overfitting to this exact one-sample OCR artifact (unlike the two fixes
    above, this isn't a case of the sentence using a placeholder/shorthand
    the letterhead-fallback mechanism already exists to handle -- the
    sentence's own words are the real name, just with one word garbled).
    Left as an honest, named OCR-quality limitation rather than a fabricated
    fix, consistent with this codebase's standing real-sample-first
    discipline.
    """

    document_type = AnalyzedDocumentType.AUTHORITY_LETTER

    #: Backward-reference phrases the "on behalf of X" sentence sometimes
    #: uses instead of literally naming the organization (confirmed real,
    #: GDA Abbotabad: "...on behalf of this\nAuthority." captures just
    #: "this"). Triggers the letterhead fallback in extract() below. The
    #: bare "directorate" alternative is a different real shape (confirmed
    #: 2026-08-26, DG Sports): no demonstrative at all, just a generic
    #: organizational-unit noun standing in for the real name ("...on the
    #: behalf of Directorate.") -- same underlying phenomenon (self-
    #: referential shorthand instead of the real name), different surface
    #: form, so it's a genuine addition to this same mechanism rather than a
    #: separate one.
    _GENERIC_ORG_REFERENCE = re.compile(
        r"^(?:(?:this|the(?:\s+said)?|said)(?:\s+(?:authority|board|office|department))?"
        r"|directorate)$",
        re.IGNORECASE,
    )
    #: Letterhead lines to skip when falling back -- contact details, not
    #: the organization's own name.
    _LETTERHEAD_SKIP = re.compile(
        r"^(?:Ph|Phone|Fax|Email|Govt\.?|Government)\b",
        re.IGNORECASE,
    )
    #: A job-title heading line, not the organization's own name -- confirmed
    #: real 2026-08-26 across two independent TMA departments (TMA Lal Qilla
    #: Dir Lower, TMA Samarbagh Dir Lower), both of whose letterheads open
    #: with "OFFICE OF THE TEHSIL MUNICIPAL OFFICE(R)" before the actual
    #: organization name ("TEHSIL MUNICIPAL ADMINISTRATION <place>") on the
    #: next line(s). Scoped to the confirmed real shape -- the whole line
    #: starts with "OFFICE OF THE" and itself ends in "OFFICE"/"OFFICER" --
    #: not a general "OFFICE OF THE" prefix skip, since that phrase can also
    #: open a letterhead that *is* naming the real organization (confirmed
    #: real, the Zoo sample: "OFFICE OF THE CONSERVATOR WILDLIFE, PESHAWAR
    #: ZOO", which does not end in "OFFICE"/"OFFICER" and must not be
    #: skipped).
    _OFFICE_TITLE_HEADER = re.compile(
        r"^OFFICE OF THE\b.*OFFICE[R]?$",
        re.IGNORECASE,
    )
    #: A demonstrative-only backward reference ("this"/"the"/"the said"/
    #: "said"), as opposed to a bare generic noun like "directorate" --
    #: used to decide which word of a matched ``_GENERIC_ORG_REFERENCE``
    #: value is worth searching the letterhead for (see ``_anchor_word_for``
    #: below).
    _DEMONSTRATIVE_ONLY = re.compile(r"^(?:this|the(?:\s+said)?|said)$", re.IGNORECASE)

    _patterns = {
        "focal_person_name": re.compile(
            r"(?:Mr|Mrs|Ms|Dr)\.?\s+([A-Za-z][A-Za-z.'\- ]*?)"
            r"(?=\s*[,(]|\n[^\n,()]{0,80}[,(]|\s+CNIC|\s+is\s+authorized)",
        ),
        "focal_person_designation": re.compile(
            r"(?:Mr|Mrs|Ms|Dr)\.?\s+[A-Za-z][A-Za-z.'\- ]*?"
            r"(?:[,(]|\n(?=[^\n,()]{0,80}[,(]))\n?\s*([^,()]+?)(?=[,()]|\s+is\s+authorized)",
            re.IGNORECASE,
        ),
        "organization_name": re.compile(
            r"on\s+(?:the\s+)?behalf\s+of\s+([^.\n]+(?:\n[^.\n]+)?)",
            re.IGNORECASE,
        ),
        "account_holder": re.compile(
            r"(?:Account Title|Account Holder|Account Name)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_number": re.compile(
            r"(?:Account Number|A/?C No\.?|Account No\.?)\s*[:|-]?\s*([A-Za-z0-9\-/ ]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "iban": re.compile(
            r"\bIBAN\b\s*[:|-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})",
            re.IGNORECASE,
        ),
    }

    def extract(self, text: str) -> dict[str, Any]:
        fields = super().extract(text)
        org = fields.get("organization_name")
        if org:
            org = re.sub(r"\s+", " ", org).strip()
            if self._GENERIC_ORG_REFERENCE.match(org):
                anchor = self._anchor_word_for(org)
                fallback = self._letterhead_organization_name(text, anchor_word=anchor)
                if fallback:
                    fields["organization_name"] = fallback
                else:
                    del fields["organization_name"]
            else:
                fields["organization_name"] = org
        return fields

    @classmethod
    def _anchor_word_for(cls, org: str) -> str | None:
        """Return the one real word of a generic org reference worth
        searching the letterhead for, or ``None``.

        A bare generic noun with no demonstrative ("Directorate") is itself
        the anchor -- it's the word the letterhead is expected to open with
        (confirmed real, DG Sports: "DIRECTORATE GENERAL OF SPORTS"). A
        demonstrative-plus-noun value ("this Authority", "the Authority")
        anchors on the trailing noun instead, since the demonstrative itself
        never appears in a real letterhead. A bare demonstrative alone
        ("this"/"the"/"said", no noun) has no anchor -- there's nothing
        specific enough left to search for, so the caller falls back to the
        first substantive letterhead line instead (the original mechanism,
        still correct for GDA Abbotabad and every other real sample that
        never reaches this path with a noun at all).
        """
        words = org.split()
        if len(words) == 1:
            return words[0]
        prefix = words[0] if len(words) == 2 else " ".join(words[:2])
        if cls._DEMONSTRATIVE_ONLY.match(words[0]) or cls._DEMONSTRATIVE_ONLY.match(prefix):
            return words[-1] if len(words) > 1 else None
        return None

    @classmethod
    def _letterhead_organization_name(
        cls, text: str, *, anchor_word: str | None = None
    ) -> str | None:
        """Return the real letterhead organization name, or ``None``.

        Scans the text before the "AUTHORITY LETTER" title for substantive
        lines -- not blank, not contact info, not a job-title heading line
        (``_OFFICE_TITLE_HEADER``), long enough to plausibly be an
        organization name rather than an OCR artifact (confirmed real: GDA
        Abbotabad's letterhead has a stray one-character line above the org
        name).

        When ``anchor_word`` is given (the real word a generic "on behalf of
        X" reference used instead of the actual name -- see
        ``_anchor_word_for``), prefers the first substantive line that
        contains it, since that's a stronger, more specific signal than
        positional order alone (confirmed real, DG Sports: the letterhead's
        very first substantive line is an unrelated slogan, "Sports are
        essential for the development of a happy, healthy & vigorous
        society," which the anchor word "directorate" correctly skips past
        to reach "DIRECTORATE GENERAL OF SPORTS"). Falls back to the first
        substantive line when no anchor is given or none matches -- the
        original mechanism, unchanged for every sample that doesn't need
        the anchor.

        A candidate ending in "Administration" is joined with the next
        substantive line -- confirmed real and structurally consistent
        across multiple independent TMA samples (not just the ones this was
        built against) that "Tehsil Municipal Administration" is always
        followed by a place-name completing the real organization name on
        its own next letterhead line, never a complete name by itself.
        """
        header = text.split("AUTHORITY LETTER", 1)[0]
        candidates = []
        for line in header.splitlines():
            candidate = line.strip()
            if (
                len(candidate) < 8
                or cls._LETTERHEAD_SKIP.match(candidate)
                or "@" in candidate
                or cls._OFFICE_TITLE_HEADER.match(candidate)
            ):
                continue
            candidates.append(candidate)
        if not candidates:
            return None
        if anchor_word:
            for candidate in candidates:
                if re.search(r"\b" + re.escape(anchor_word) + r"\b", candidate, re.IGNORECASE):
                    return candidate
        result = candidates[0]
        if result.upper().endswith("ADMINISTRATION"):
            index = candidates.index(result)
            if index + 1 < len(candidates):
                result = f"{result} {candidates[index + 1]}"
        return result


class BusinessRequirementDocumentExtractor(RegexExtractor):
    """Extracts presence signals from a Business Requirement Document (BRD).

    docs/Master_Rules_Combined.md Section 10 requires the BRD to (a) confirm
    that payments are required to be digitized and (b) identify/list the
    revenue-generating services being digitized. Real BRDs (three independent
    departments, Confidential Data/) satisfy both requirements but express
    them with no shared template at all -- unlike Bilateral Agreement or
    Authority Letter, there is no labeled field or single consistent sentence
    grammar here; department history, section headers and list format (a
    numbered list, a categorized bullet breakdown, or unstructured prose all
    turned up across the three samples) differ per department. So neither
    field extracts a *value* in the usual sense -- both are presence
    detectors whose captured group is the anchor phrase that triggered them,
    kept as the field's value for a human reviewer's context.

    digitization_intent_confirmed is anchored on "KPITB('s) Fin(-)Tech Unit"
    -- confirmed verbatim (case/spacing aside) in all three real samples,
    the one genuinely consistent element, the same way Authority Letter had
    one consistent core sentence. See constants.CRITICAL_FIELDS for why only
    this field, not revenue_services_listed, is treated as critical.
    """

    document_type = AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT

    _patterns = {
        "digitization_intent_confirmed": re.compile(
            r"(KPITB'?S?\s+Fin\s*Tech\s+Unit|Khyber\s+Pakhtunkhwa\s+Information\s+Technology\s+Board\s*\n?\(?KPITB\)?)",
            re.IGNORECASE,
        ),
        "revenue_services_listed": re.compile(
            r"((?:sources? of income|services offered|revenue[- ]generating services|prescribed fees?)[^\n]*(?:\n[^\n]+){0,7})",
            re.IGNORECASE,

        ),
    }


class OneLinkLetterExtractor(RegexExtractor):
    """Extracts fields from whatever real-world document lands in the 1-Link
    Letter checklist slot.

    Real content doesn't match docs/Master_Rules_Combined.md Section 4's
    KYC-style form spec -- see CONTEXT.md for the full mismatch and the
    splitter root cause. This extractor is grounded in what's actually
    there (a signed "PARTICIPATION MEMORANDUM..."), not the unvalidated
    spec, and deliberately stays narrow: department decision, 2026-08-19
    (see CONTEXT.md) -- extract only what's clearly critical and reliably
    present, not every rulebook-vs-real-world variant of this document.

    organization_name is anchored on "<ORG NAME> hereby authorizes 1LINK to
    take actions" (clause x), confirmed present in all 4 real samples so
    far. Deliberately case-sensitive: the org name is consistently ALL CAPS
    in this sentence, and a case-insensitive match pulls in unrelated
    lower-case prose ahead of it instead (confirmed while developing this
    pattern).

    The capture group's character class gained lowercase letters 2026-08-26
    (was ``[A-Z,.\\s]``, now ``[A-Za-z,.\\s]``) -- confirmed real bug: a
    single stray-lowercase OCR misread inside an otherwise-uppercase org
    name (TMA_Khal_Dir_Lower's real text reads "TEHsIL\\nMUNICIPAL
    ADMINISTRATION KHALL hereby authorizes...", a misread "s") blocked the
    match from starting at the real name's first letter at all, so Python's
    leftmost-match search instead started two characters later, truncating
    the captured value down to "IL MUNICIPAL ADMINISTRATION KHALL". This is
    a different, narrower change than the case-insensitive experiment
    warned about in the paragraph above: this pattern's overall
    ``re.IGNORECASE`` flag is untouched (still off, so the literal "hereby
    authorizes...to take actions" anchor stays exactly as strict as
    before), and the capture group is still non-greedy with that exact
    literal string required immediately after it -- so the safety property
    that matters here (the match can't run past the real org name without
    immediately finding that literal continuation) is unchanged. Verified
    against all 23 real ONE_LINK_LETTER cached samples: the known-buggy
    match now returns the complete real text verbatim, including that
    same real OCR misread ("TEHsIL MUNICIPAL ADMINISTRATION KHALL", lower-
    case "s" and all -- the fix stops the truncation, it does not silently
    correct OCR noise the source text itself contains). 3 more real samples
    (TMA_Thall_Hangu, TMA_Samarbagh_Dir_Lower -- whose real text has two
    separate stray-lowercase misreads, "TEs\\nMUNICIPAL ADMINIsTRATION,
    SAMARBAGH" -- and DG_Sports_KP_Onboarding_Documents, a misread
    "Pakhtunkliwa") had the identical latent bug shape on their own real
    OCR noise and are now also fixed; every other real match and every
    real empty result is unchanged.

    No IBAN/account field, despite that being the department's stated
    focus: tested directly against real cached text before deciding.
    TMA_Lal_Dir_Upper's real sample has exactly one unambiguous IBAN;
    GDA_Abbotabad's real sample lists a 5-bank reference table with no
    textual indication of which one is operative -- the same ambiguity
    that already keeps branch_code (removed here) out of the critical set.
    RegexExtractor.extract() takes the first regex match unconditionally;
    it has no way to detect "more than one candidate exists" and fall back
    to honestly missing, so a plain IBAN pattern would silently return the
    wrong one of five real banks on that shape. Building the disambiguation
    needed to do this safely is exactly the kind of variant-by-variant
    validation this decision says to stop doing -- left out rather than
    added half-working.
    """

    document_type = AnalyzedDocumentType.ONE_LINK_LETTER

    _patterns = {
        "organization_name": re.compile(
            r"([A-Z][A-Za-z,.\s]{3,60}?)\s+hereby authorizes [1I]\s*LINK to take actions"
        ),
    }

    _post = {
        "organization_name": _as_single_line,
    }


class CnicFrontExtractor(RegexExtractor):
    """Extracts fields from a real Pakistani CNIC's front face.

    Front only -- DocumentType.CNIC_BACK has zero real samples anywhere in
    this session's cache (see CONTEXT.md), so back-face extraction is not
    attempted; a back upload still falls through to the generic ID_DOCUMENT
    classifier exactly as it did before this extractor existed.

    Built against 3 real cached samples (Confidential Data/.ocr_cache/,
    DG_Sports_KP_Onboarding_Documents__CNIC_FRONT_copy1/2/3.txt), all one
    organization -- real organizational diversity here is 1, not 3, stated
    honestly rather than implied. 2 of the 3 samples OCR'd with a clean,
    consistently ordered label-then-value layout (each label line immediately
    followed by its value line, or -- for adjacent label pairs like "Identity
    Number"/"Date of Birth" -- a label-block immediately followed by a
    value-block in the same order). The third sample OCR'd with the labels
    and values scrambled out of that order entirely (a genuinely different
    OCR read-order, not corrupted content -- copy2's contamination, documented
    separately in CONTEXT.md, is a distinct splitter merge-artifact bug, not
    this same issue). Every pattern below is anchored on the *clean* layout
    shape; on the scrambled sample a field either still happens to line up
    (document_number, full_name) or honestly misses (date_of_expiry) rather
    than risk pairing a label with the wrong value -- the same failure-
    avoidance principle as AMC's "/IBAN" garbage-capture lesson and 1-Link
    Letter's multi-bank-table miss.

    document_number is anchored purely on the canonical CNIC shape
    (5-7-1 digit groups, hyphen-separated) with no label dependency at all,
    so it is the one field that also extracts correctly on the scrambled
    sample -- confirmed against all 3 real samples. Deliberately named
    document_number, not cnic_number, to reuse
    app.rule_engine.rules.format_rules.FormatCnicRule's existing format
    validation (field_names=("document_number", "tax_reference_number")) for
    free, the same way branch_code was named to match CrossBranchCodeRule.

    full_name is anchored on a line that is exactly "Name" (not "Father
    Name", which the exact-line anchor deliberately excludes) followed by
    its value on the next line. Confirmed correct on all 3 real samples,
    including the scrambled one, where this specific label happened to still
    sit directly before its value despite everything else being out of
    order -- real evidence, not an assumption that the pattern generalizes.
    father_name was not attempted: the identical anchor shape only holds on
    2 of 3 samples for that label, and with only one real organization on
    file there isn't enough evidence yet to judge whether that is a real
    OCR-order pattern or coincidence.

    date_of_expiry is anchored on the exact two-line label block "Date of
    Issue" then "Date of Expiry" being immediately followed by a two-line
    value block, taking the second value as the expiry date. Confirmed
    correct on the 2 clean samples (both show a 10-year gap between the
    captured issue and expiry values, consistent with real CNIC validity
    periods -- a plausibility check, not proof, but supportive). Honestly
    misses on the scrambled sample, where this block shape does not occur
    intact. date_of_birth and date_of_issue were not attempted this pass to
    keep the first real-sample-validated version scoped to what
    docs/Master_Rules_Combined.md Section 12 actually asks for by name
    (format, expiry, readability, consistency) rather than extracting every
    field just because the layout partially allows it.
    """

    document_type = AnalyzedDocumentType.CNIC_FRONT

    _patterns = {
        "document_number": re.compile(r"\b(\d{5}-\d{7}-\d)\b"),
        "full_name": re.compile(r"(?m)^Name[ \t]*$\r?\n(.+)$"),
        "date_of_expiry": re.compile(
            r"(?m)^Date of Issue[ \t]*$\r?\n^Date of Expiry[ \t]*$\r?\n"
            r"[\d.]+[ \t]*\r?\n([\d.]+)"
        ),
    }

    _post = {
        "date_of_expiry": _as_iso_date_dotted,
    }


class FormalRequestLetterExtractor(RegexExtractor):
    """Extracts structured fields from a Formal Request Letter.

    Built against the one real sample on file (confirmed 2026-08-18, TMA Lal
    Dir Upper) -- previously absorbed silently into the ONE_LINK_LETTER
    group by the splitter (see splitter._STRONG_TITLE_PHRASES) since its
    real subject line ("REQUEST FOR DIGITAL ACCOUNT AND FOR ONLINE
    PAYMENTS") never matched the spec-guessed "FORMAL REQUEST LETTER"/
    "FORMAL REQUEST" phrases.

    organization_name originally captured only the office-holder title on
    the anchor's own line ("OFFICE OF THE <title>") instead of the real
    organization name one line below it; the pattern now explicitly
    discards the anchor's own line and captures the next one, which is
    where the one real sample states it. Not validated against any other
    anchor variant (DEPARTMENT OF/GOVERNMENT OF/TO THE/FROM) -- none has a
    real sample yet, so this shape is assumed to generalize, not confirmed.

    focal_person_designation previously bled across a line boundary: the
    bare word "Title" inside the real sample's "Account Title" table header
    (no colon) satisfied the old permissive `\\s*[:|-]?\\s*` gap, which
    happily crossed the newline into the next line's unrelated table
    content ("IBAN/Account No") and returned it as a designation. The
    pattern now requires an explicit `:`/`|`/`-` delimiter and keeps the
    surrounding whitespace on the same line, so a bare label-shaped
    substring with nothing after it can no longer match at all. This
    correctly leaves the field missing on the one real sample -- it never
    states a designation for its focal person -- an honest gap, not
    something this pattern should paper over.

    date is a known, still-open honest miss on the one real sample: the
    real text reads "Dated Dir(U) 13/07/2026" (unrelated words between the
    label and the date) and, separately, "Dated: 14-04-2026" referring to a
    third-party letter being cited, not this letter's own date -- neither
    fits this pattern's strict label-then-date shape, and matching the
    second would be actively wrong (the wrong letter's date). Not touched
    this pass.
    """

    document_type = AnalyzedDocumentType.FORMAL_REQUEST_LETTER

    _patterns = {
        "organization_name": re.compile(
            r"(?:OFFICE OF THE|DEPARTMENT OF|GOVERNMENT OF|TO THE|FROM[:|-]?)[^\n]*\n\s*(.+)",
            re.IGNORECASE,
        ),
        "addressee": re.compile(
            r"To,?\s*\n?\s*(The\s+Managing\s+Director[^\n,]*|Managing\s+Director[^\n,]*|KPITB[^\n,]*|Khyber\s+Pakhtunkhwa\s+Information\s+Technology\s+Board[^\n,]*)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "subject": re.compile(
            r"Subject\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "date": re.compile(
            r"(?:Date|Dated)\s*[:|-]?\s*([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[0-9]{4}[/\-.][0-9]{1,2}[/\-.][0-9]{1,2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",
            re.IGNORECASE | re.MULTILINE,
        ),
        "focal_person_name": re.compile(
            r"(?:Focal Person Name|Focal Person|Contact Person|Authorized Representative|Submitted By|Signed By)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "focal_person_designation": re.compile(
            r"(?:Designation|Title)[ \t]*[:|-][ \t]*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {
        "date": _as_iso_date,
    }


#: Detection keywords per analysed document type. Weights express how strongly a
#: keyword identifies the type; scoring is order-independent and deterministic.
_DETECTION_KEYWORDS: dict[AnalyzedDocumentType, list[tuple[str, int]]] = {
    AnalyzedDocumentType.BANK_STATEMENT: [
        ("account statement", 3),
        ("bank statement", 3),
        ("opening balance", 2),
        ("closing balance", 2),
        ("iban", 2),
        ("transactions", 1),
    ],
    AnalyzedDocumentType.PAYSLIP: [
        ("payslip", 3),
        ("pay slip", 3),
        ("salary slip", 3),
        ("gross salary", 2),
        ("net salary", 2),
        ("payment date", 1),
        ("employee id", 1),
    ],
    AnalyzedDocumentType.ID_DOCUMENT: [
        ("national id", 3),
        ("identity card", 3),
        ("passport", 3),
        ("date of birth", 2),
        ("expiry date", 2),
        ("id number", 1),
    ],
    AnalyzedDocumentType.TAX_DOCUMENT: [
        ("tax return", 3),
        ("tax reference", 2),
        ("taxpayer", 2),
        ("tax year", 2),
        ("income tax", 1),
    ],
}

#: Every real Account Maintenance Certificate sample (Confidential Data/
#: .ocr_cache/, 7 files across 4 independent banks) states its own issue/
#: letter date somewhere in the header, before the certifying sentence
#: ("This is to certify...", "It is certified that...", "We hereby
#: certified...", "This certificate is/has been issued..."). Bounding the
#: date search to that header zone -- rather than the whole document -- is
#: the fix for two confirmed real false positives a whole-document search
#: hits: a "Date of Account Opening" label (a different field, always
#: further down, in the account-detail block) and, on one real sample, a
#: scanned CNIC copy's own "Date of Issue" field embedded later in the same
#: OCR text with a different value. The boundary itself matches "certif"
#: rather than "certificate", with a lookbehind skipping the one place that
#: word appears earlier than intended: the document's own title line,
#: "ACCOUNT MAINTENANCE CERTIFICATE"/"Account Maintenance Certificate",
#: which would otherwise truncate the zone before the real date on samples
#: where the date follows the title.
_AMC_CERTIFYING_CLAUSE_RE = re.compile(r"(?<!Maintenance )certif", re.IGNORECASE)

#: A date-shaped token covering the four real formats confirmed across the
#: corpus: dash DD-MM-YYYY (GDA_Abbotabad copy3), dot DD.MM.YYYY
#: (GDA_Abbotabad copy2), slash DD/MM/YYYY (GDC_Madyan_Swat), "DD Month[,]
#: YYYY" (account_maintennace_certificate, DG_Sports -- no comma) and
#: "Month DD, YYYY" (GDA_Abbotabad copy4). Requiring the *value* to look
#: like a date -- not just "some text before the next line break" -- is
#: what keeps this from matching a ledger-table "DATE" column header or the
#: certificate's own title (both real, confirmed decoys) even without the
#: header-zone bound below.
_AMC_DATE_TOKEN = (
    r"(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
)

#: A labeled date within the header zone, tried first. Deliberately
#: includes bare "Dated"/"Date" (not just "Date of Issue"/"Issue Date"/...):
#: 3 of the 7 real samples label their issue date with nothing more
#: specific than "Date:" or "Dated:". Requiring the value to match
#: ``_AMC_DATE_TOKEN`` (rather than "any text up to the next line break")
#: is what keeps a bare "Date" from matching "Date of Account Opening" --
#: the non-date continuation ("of Account Opening...") simply fails the
#: value shape, so the match attempt fails at that position and search()
#: continues past it to a real date elsewhere (or finds none).
_AMC_ISSUE_DATE_LABEL_RE = re.compile(
    r"(?:Date of Issue|Issue Date|Issued On|Issuance Date|Dated|Date)"
    r"\s*[:\-]*\s*"
    r"(" + _AMC_DATE_TOKEN + r")",
    re.IGNORECASE,
)

#: Fallback for the 2 real samples with no date label at all (DG_Sports,
#: account_maintennace_certificate): the issue date sits unlabeled, on its
#: own line, in the bank's letterhead. Confined to the same header zone as
#: the labeled pattern, so it can't reach the decoys that pattern is
#: guarded against.
_AMC_ISSUE_DATE_FALLBACK_RE = re.compile(r"\b(" + _AMC_DATE_TOKEN + r")\b")


def _parse_amc_issue_date(raw: str) -> str | None:
    """Parse an Account Maintenance Certificate issue date.

    Deliberately separate from :func:`_parse_date`/:func:`_as_iso_date`:
    this field's real samples use two formats those don't cover -- dot-
    separated (``DD.MM.YYYY``) and comma-joined month names in either order
    (``Month DD, YYYY`` / ``DD Month, YYYY``) -- and extending the shared
    parser would change parsing behaviour for every other extractor that
    reuses it, for formats never confirmed against this field's own real
    samples.
    """
    value = re.sub(r"\s+", " ", raw.strip())
    for fmt in (
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B, %Y",
        "%d %b, %Y",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_amc_issue_date(text: str) -> str | None:
    """Return the certificate's own issue/letter date, or ``None``.

    Confined to the header zone (text before the certifying sentence -- see
    ``_AMC_CERTIFYING_CLAUSE_RE``), so this can never reach the real decoys
    that live further down a real document (a "Date of Account Opening"
    field, or -- on one real sample -- a different, later document embedded
    in the same OCR text). Tries a labeled match first, then a bare
    date-shaped token for the 2 real samples with no label at all.
    """
    boundary = _AMC_CERTIFYING_CLAUSE_RE.search(text)
    zone = text[: boundary.start()] if boundary is not None else text
    match = _AMC_ISSUE_DATE_LABEL_RE.search(zone) or _AMC_ISSUE_DATE_FALLBACK_RE.search(zone)
    if match is None:
        return None
    return _parse_amc_issue_date(match.group(1))


class AccountMaintenanceCertificateExtractor(RegexExtractor):
    """Extracts structured fields from an Account Maintenance Certificate.

    A bank certificate attesting an account's details: account title, account
    number, IBAN, issuing bank and branch. Field names deliberately mirror the
    cross-document consistency rules (``account_holder``, ``account_number``,
    ``iban``) so the normalization stage can compare them against the Bilateral
    and Tripartite agreements.

    account_holder/account_number/iban are produced by the structural
    ``_extract_bank_account_block`` parser rather than the label-anchored regex
    used elsewhere: the real cached layouts (Confidential Data/.ocr_cache/,
    four independent bank certificates) interleave label and value lines in
    shapes a single regex cannot capture without garbage-capture. Two concrete
    real bugs this fixes, both confirmed before the change: the combined
    ``Account No/IBAN`` label captured ``/IBAN`` as the account number, and a
    dotted-leader ``ACCOUNT NUMBER:...`` label failed its separator, so the
    account number leaked in from an unrelated certificate later in the file.

    issue_date is produced by ``_extract_amc_issue_date`` rather than a plain
    ``_patterns`` entry, for the same reason: real layouts vary too much for
    one unguarded regex. Before 2026-08-26 the field matched only "Date of
    Issue"/"Issue Date"/"Issued On"/"Issuance Date" anywhere in the whole
    document, which produced a wrong value on real samples in two confirmed
    ways -- matching a ledger-table "DATE" column header, and matching a
    scanned CNIC copy's own "Date of Issue" field elsewhere in the same OCR
    text -- while still missing the date entirely on samples that label it
    with nothing more specific than a bare "Date:"/"Dated:", or don't label
    it at all. Of the 7 real cached samples, 6 now resolve to their correct
    real date; the 7th (GDA_Abbotabad copy1) has no safe fix: its issue date
    is present in the source but OCR-mangled into single digits split across
    consecutive lines ("2\\n2\\n0\\n4\\n2\\n0\\n2\\n6") before the "Date of
    Issue:" label instead of after it, which is an OCR-quality problem, not
    a labeling one -- reconstructing it would be a fragile, one-sample-only
    hack, not a generalizable fix.

    closing_balance (added 2026-09-03) reuses BankStatementExtractor's
    already-proven "Closing Balance" pattern verbatim rather than a new
    one: not part of the original field set above (this class previously
    only extracted account_holder/account_number/iban/bank_name/
    branch_name/issue_date -- no balance field at all). Confirmed on the
    real TMA Khal Dir Lower sample (The Bank of Khyber statement), only
    one real sample validated so far -- same not-yet-fully-verified status
    as the ACCOUNT_MAINTENANCE_CERTIFICATE bank-name splitter entries
    added the same session (see splitter.py), re-check against more real
    samples once available.
    """

    document_type = AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE

    _patterns = {
        "bank_name": re.compile(
            r"\bBank(?: Name)?\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "branch_name": re.compile(
            r"(?:Branch Name|Branch)\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        # Reuses the exact pattern already proven on BankStatementExtractor
        # above rather than inventing a new one blind: real AMC layouts
        # (confirmed on TMA Khal Dir Lower, "The Bank of Khyber" statement)
        # state this as a two-line table cell -- "Closing Balance" on its
        # own line, the amount on the next -- with no colon separator. The
        # `[:|-]?` separator is optional and `\s*` already spans the
        # intervening newline, so the same pattern matches this layout
        # without changes.
        "closing_balance": re.compile(
            r"(?:Closing Balance|Closing)\s*[:|-]?\s*([€£$]?\s?[\d.,]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    _post = {"closing_balance": _as_float}

    def extract(self, text: str) -> dict[str, Any]:
        fields = super().extract(text)
        block = _extract_bank_account_block(text)
        for key in ("account_holder", "account_number", "iban"):
            if key not in fields and key in block:
                fields[key] = block[key]
        issue_date = _extract_amc_issue_date(text)
        if issue_date is not None:
            fields["issue_date"] = issue_date
        return fields


class TripartiteAgreementExtractor(RegexExtractor):
    """Extracts structured fields from a Tripartite Agreement.

    Captures the three named parties (1-Link, KPITB, the sub-biller) and the
    bank details section (account title, account number, branch) that must
    match the Account Maintenance Certificate. Field names follow the
    cross-document consistency rules (``account_holder``, ``account_number``,
    ``branch_code``).

    account_holder/account_number come from the structural
    ``_extract_bank_account_block`` parser: the one real sample validated
    (Confidential Data/.ocr_cache/) states the bank details as a stacked column
    table whose header block ("S# / Bank Name / IENT / Account Title / IBAN/
    Account No") is positionally mapped onto the value block. Before the change
    the greedy label-anchored regex captured the header ``IBAN/Account No`` as
    account_holder and the row index ``01`` as account_number -- confirmed
    garbage before fixing.

    party_subbiller was previously anchored on the first "(...)" parenthetical
    containing "sub-biller", on the assumption real documents define the
    sub-biller party the same way ``party_1link``/``party_kpitb`` do
    ("...(hereinafter referred to as 'X')"). Confirmed real bug 2026-08-26
    (see CONTEXT.md): the one real sample on file, TMA_Thall_Agreement, only
    contains two such parentheticals anywhere in the document, and neither
    names the sub-biller -- one is fixed legal boilerplate ("...a copy of
    which (barring commercials, at discretion of sub biller/bill
    aggregator) will be provided to 1LINK."), and the other is the
    template's own unfilled placeholder, ``(Sub Biller Name)``, never
    replaced with a real name in this signed document. The old pattern's
    leftmost, non-greedy search always lands on the first (boilerplate) one,
    which is why it silently produced generic contract prose instead of an
    honest miss or a real name.

    The real sub-biller name is stated repeatedly in plain prose throughout
    the document (e.g. "The Tehsil Municipal Administration THALL hereby
    irrevocably undertakes, agrees and acknowledges that..."), never inside
    a parenthetical at all. Re-anchored on that clause instead. This is not
    single-sample-derived: "<org name> hereby irrevocably undertakes" is a
    fixed clause from the same real, shared 1LINK Participation Memorandum
    template that this document's sub-biller section is built from --
    confirmed present, correctly naming the real org, across 11 other real
    cached files spanning at least 8 independent organizations (currently
    cached under the unrelated ``ONE_LINK_LETTER`` type due to splitter
    history, not this type, but the underlying template text and clause
    are identical). Structurally the same safe shape as
    ``OneLinkLetterExtractor.organization_name``'s already-fixed pattern:
    non-greedy with a required, unchanged literal continuation immediately
    after the capture, so the match cannot run past the real name into
    unrelated text. The single-real-Tripartite-sample constraint from the
    2026-08-25/26 coverage audit still genuinely limits how confidently this
    exact *field mapping* (Tripartite's party_subbiller specifically) is
    validated -- see CONTEXT.md for the honest caveat.
    """

    document_type = AnalyzedDocumentType.TRIPARTITE_AGREEMENT

    #: Patterns are label-anchored and deliberately tolerant of OCR noise:
    #: party names are captured up to the next comma, newline or the standard
    #: "(hereinafter referred to as ...)" clause. Tune against real samples.
    _patterns = {
        "party_1link": re.compile(
            # Negative lookbehind excludes the Authority Letter boilerplate
            # "...matters related to 1-Link and the KPITB on behalf of..."
            # which appears at the top of compound Tripartite Agreement files
            # before the real party-definition section. The lookbehind is
            # fixed-width (11 chars) as required by the re module.
            r"(?<!related to )((?:1\s*LINK|1-LINK|ONE[-\s]?LINK|ONELINK)[^,\n]*?)(?=\s*\(hereinafter|\s*,|\s*\n|$)",
            re.IGNORECASE,
        ),
        "party_kpitb": re.compile(
            r"((?:KHYBER PAKHTUNKHWA INFORMATION(?:\s*(?:&|AND))?\s*TECHNOLOGY BOARD|KPITB))(?=[\s,])",
            re.IGNORECASE,
        ),
        "party_subbiller": re.compile(
            r"(?-i:([A-Z][A-Za-z0-9 ,&'()\-/]*?))\s+hereby irrevocably undertakes",
            re.IGNORECASE,
        ),
        "account_holder": re.compile(
            r"(?:Account Title|Title of Account|Account Holder)\s*[:|-]?\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "account_number": re.compile(
            r"(?:Account Number|A/?C No\.?|Account No\.?)(?:\s*\(IBAN\))?\s*[:|-]?\s*(?:(?:[^A-Z0-9\n]*\n[^A-Z0-9\n]*.*?(?:\|[ \t]*)?)?([A-Z0-9]{10,30}))",
            re.IGNORECASE | re.MULTILINE,
        ),
        "branch_code": re.compile(
            r"(?:Branch Code|Branch)\s*:\s*(.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    }

    def extract(self, text: str) -> dict[str, Any]:
        # Structural parser takes precedence for account_holder/account_number
        # (it correctly handles the stacked column-table and interleaved
        # label/value layouts seen in real cached samples): its results
        # overwrite the label-anchored regex captures, which are garbage on
        # those layouts (headers, row indexes). The regex patterns remain for
        # every other field (party_*, branch_code) and as the only source for
        # account fields on layouts the structural parser does not recognize
        # (e.g. pipe-separated table rows). Only the two account keys are
        # merged from the block so structural-only extras (iban) never leak
        # into Tripartite's field set.
        fields = super().extract(text)
        block = _extract_bank_account_block(text)
        for key in ("account_holder", "account_number"):
            if key in block:
                fields[key] = block[key]
        return fields


#: Extractors available for each analysed document type.
_EXTRACTORS: dict[AnalyzedDocumentType, RegexExtractor] = {
    AnalyzedDocumentType.BANK_STATEMENT: BankStatementExtractor(),
    AnalyzedDocumentType.PAYSLIP: PayslipExtractor(),
    AnalyzedDocumentType.ID_DOCUMENT: IdentityExtractor(),
    AnalyzedDocumentType.TAX_DOCUMENT: TaxExtractor(),
    AnalyzedDocumentType.BILATERAL_AGREEMENT: BilateralAgreementExtractor(),
    AnalyzedDocumentType.AUTHORITY_LETTER: AuthorityLetterExtractor(),
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: AccountMaintenanceCertificateExtractor(),
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: TripartiteAgreementExtractor(),
    AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT: BusinessRequirementDocumentExtractor(),
    AnalyzedDocumentType.ONE_LINK_LETTER: OneLinkLetterExtractor(),
    AnalyzedDocumentType.CNIC_FRONT: CnicFrontExtractor(),
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: FormalRequestLetterExtractor(),
}


def detect_document_type(text: str) -> AnalyzedDocumentType:
    """Infer the analysed document type from keyword scoring.

    Every keyword present in the text contributes its weight to the matching
    document type; the type with the highest total wins. Ties resolve to the
    first-defined type, keeping the result deterministic.

    Deliberately only recognises the 4 categories with a real extractor
    below -- it is not, and should not become, a classifier for the real
    required-document checklist (Tripartite Agreement, Authority Letter,
    etc.). That vocabulary belongs to the splitter
    (``app/preprocessing/splitter.py``) and is already reliably captured on
    ``document.document_type``; widening this table to match it without
    adding a real extractor for each type would only relabel documents this
    module still can't extract anything from. When this returns ``UNKNOWN``,
    ``DocumentAnalysisService`` falls back to the splitter's own
    classification to distinguish "recognised, no extractor yet" from
    "genuinely couldn't classify" -- see
    ``DocumentAnalysisService._recognized_checklist_type``.

    Args:
        text: Raw OCR text of the document.

    Returns:
        The inferred analysed document type, or ``UNKNOWN``.
    """
    lowered = text.lower()
    best_type = AnalyzedDocumentType.UNKNOWN
    best_score = 0
    for document_type, keywords in _DETECTION_KEYWORDS.items():
        score = sum(weight for keyword, weight in keywords if keyword in lowered)
        if score > best_score:
            best_score = score
            best_type = document_type
    return best_type


def extract_fields(text: str, document_type: AnalyzedDocumentType) -> dict[str, Any]:
    """Extract normalized fields from ``text`` for an analysed document type.

    Args:
        text: Raw OCR text of the document.
        document_type: Analysed document type selecting the extractor.

    Returns:
        The normalized extracted fields.

    Raises:
        UnsupportedDocumentType: When the type has no extractor (e.g. unknown).
    """
    extractor = _EXTRACTORS.get(document_type)
    if extractor is None:
        raise UnsupportedDocumentType()
    return extractor.extract(text)
