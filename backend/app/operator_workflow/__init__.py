"""Operator validation workflow module.

Endpoints and services for the first-level operator queue: a business-facing
list of applications needing operator attention, plus the document-request,
operator-reject and operator-submit actions. Operators never see OCR,
normalization or other technical internals through this module.
"""

from app.operator_workflow.routes import router

__all__ = ["router"]