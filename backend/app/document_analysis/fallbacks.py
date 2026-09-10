"""AI/VLM field fallback gate for the analysis pipeline.

The extraction pipeline is deterministic (regex patterns, validators, rules and
scoring) and always runs first. AI/VLM is deliberately kept as an opt-in
*fallback* that is never the default processor: a provider is only consulted for
expected fields that the rule pipeline left missing or invalid, and only the
names of those fields (plus the document text) are sent — never an entire
document.

This module defines the provider interface, the low-confidence field selection
(the gate), and the counters that make AI usage measurable and testable. No
provider is bundled: production wires one through dependency injection, and with
``ai_fallback_enabled=false`` (the default) zero AI calls are ever made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.document_analysis.constants import AnalyzedDocumentType


class FieldFallback(Protocol):
    """A provider that resolves specific fields of one document.

    Implementations receive the document type, the raw document text, the
    fields already extracted by the rule pipeline and the subset of field names
    that need clarification, and return values for the fields they could
    resolve. Fields the provider cannot resolve are simply omitted.
    """

    def resolve(
        self,
        *,
        document_type: AnalyzedDocumentType,
        text: str,
        fields: dict[str, Any],
        field_names: list[str],
    ) -> dict[str, Any]:
        """Return resolved values for ``field_names``.

        Args:
            document_type: Analysed document type.
            text: Raw document text the provider may use as context.
            fields: Fields already extracted by the rule pipeline.
            field_names: Subset of expected fields needing clarification.

        Returns:
            A mapping of field name to resolved value; unresolved fields are
            omitted. ``None`` values are treated as unresolved.
        """


@dataclass
class AiFallbackMetrics:
    """Counters describing AI fallback usage across an analysis run.

    Attributes:
        ai_calls: Number of fallback provider invocations (one per document
            that had fields needing clarification).
        fields_requested: Number of field names sent to the provider.
        fields_resolved: Number of fields the provider actually resolved.
        failed_calls: Number of provider invocations that raised.
        fields_requiring_ai: Number of expected fields the rule pipeline left
            missing or invalid across the run — the fields the gate would send
            to a provider. Tracked even when no provider is configured.
    """

    ai_calls: int = 0
    fields_requested: int = 0
    fields_resolved: int = 0
    failed_calls: int = 0
    fields_requiring_ai: int = 0

    def snapshot(self) -> dict[str, int]:
        """Return a plain-dict snapshot for reporting and benchmarking."""
        return dict(self.__dict__)


def fields_needing_ai(
    fields: dict[str, Any],
    validation_results: list[dict[str, Any]],
    expected_fields: frozenset[str],
) -> list[str]:
    """Select the expected fields that need AI clarification.

    A field needs clarification when the rule pipeline could not extract it
    (missing) or extracted a value that failed validation (invalid). Together
    these are the low-confidence fields of the deterministic pipeline; the
    per-field confidence scoring runs later and can flag more, but the fallback
    gate must be decided here, at extraction time.

    Args:
        fields: Normalized extracted fields.
        validation_results: Per-field validation outcomes.
        expected_fields: Fields the document type is expected to carry.

    Returns:
        The sorted names of the fields needing clarification.
    """
    missing = {name for name in expected_fields if fields.get(name) is None}
    invalid = {result["field"] for result in validation_results if result["status"] == "invalid"}
    return sorted(missing | invalid)


def merge_fallback_values(
    fields: dict[str, Any],
    resolved: dict[str, Any],
    field_names: list[str],
) -> dict[str, Any]:
    """Merge provider-resolved values into the extracted fields.

    Only non-``None`` values for requested fields are accepted, so a provider
    can never overwrite rule-extracted values or introduce unrequested fields.

    Args:
        fields: Extracted fields to merge into.
        resolved: Provider-returned values.
        field_names: The fields that were requested from the provider.

    Returns:
        A new field mapping with the accepted resolutions applied.
    """
    accepted = {
        name: value
        for name, value in resolved.items()
        if name in field_names and value is not None
    }
    return {**fields, **accepted}
