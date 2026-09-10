"""Validation of human review payloads.

Keeps the review-payload rules in one place so the service layer stays thin and
the rules are unit-testable in isolation. Every violation raises an
:class:`~app.confidence.exceptions.InvalidReviewPayload`.
"""

from collections import Counter

from app.confidence.exceptions import InvalidReviewPayload
from app.confidence.schemas import ReviewDecisionType, ReviewRequest


def validate_review_request(
    request: ReviewRequest,
    flagged_fields: set[str],
) -> None:
    """Validate a review request against the fields flagged for review.

    The decisions must cover every flagged field exactly once, must not
    reference fields that were not flagged and must supply a corrected value
    whenever the decision is ``CORRECTED``.

    Args:
        request: Review payload to validate.
        flagged_fields: Names of the fields pending human review.

    Raises:
        InvalidReviewPayload: When the payload violates any of the rules.
    """
    if not flagged_fields:
        raise InvalidReviewPayload("No fields are pending human review")

    provided = [decision.field_name for decision in request.decisions]
    duplicates = [
        name for name, count in Counter(provided).items() if count > 1
    ]
    if duplicates:
        raise InvalidReviewPayload(
            f"Duplicate decisions for fields: {', '.join(sorted(duplicates))}"
        )

    unknown = sorted(set(provided) - flagged_fields)
    if unknown:
        raise InvalidReviewPayload(
            f"Decisions for fields that were not flagged for review: "
            f"{', '.join(unknown)}"
        )

    missing = sorted(flagged_fields - set(provided))
    if missing:
        raise InvalidReviewPayload(
            f"Missing decisions for flagged fields: {', '.join(missing)}"
        )

    for decision in request.decisions:
        if decision.decision is ReviewDecisionType.CORRECTED and not (
            decision.corrected_value and decision.corrected_value.strip()
        ):
            raise InvalidReviewPayload(
                f"A corrected value is required for field "
                f"'{decision.field_name}' when the decision is CORRECTED"
            )
