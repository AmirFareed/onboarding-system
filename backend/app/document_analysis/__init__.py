"""Document analysis package.

Exposes the analysis service and the REST router so the application factory can
mount the module with a single import.
"""

from app.document_analysis.routes import router
from app.document_analysis.services import DocumentAnalysisService

__all__ = ["DocumentAnalysisService", "router"]
