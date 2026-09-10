"""Performance module.

IT-only, read-only view of how long applications spend in each phase of the
lifecycle. Timing is strictly evidence-backed: every number is derived from
timestamps the system itself recorded (queue job start/completion, document
request/receipt events, review decisions) and each metric carries the list of
underlying time spans that produced it, so a user can drill from "Waiting for
documents: 3d 4h" down to each individual request/receipt pair. No time is
ever *inferred* from gaps between unrelated events: only spans that were
explicitly marked as waiting-for-documents, actively-processing, or under
review are counted.
"""

from app.performance.routes import router

__all__ = ["router"]