"""Document processing package.

Exposes the processing service and the REST router so the application factory
can mount the module with a single import.
"""

from app.document_processing.routes import router
from app.document_processing.services import DocumentProcessingService

__all__ = ["DocumentProcessingService", "router"]
