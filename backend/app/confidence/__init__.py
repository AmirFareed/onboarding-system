"""Confidence scoring package.

Exposes the confidence service and the REST router so the application factory
can mount the module with a single import.
"""

from app.confidence.routes import router
from app.confidence.services import ConfidenceService

__all__ = ["ConfidenceService", "router"]
