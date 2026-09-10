"""File upload and document management module.

Exposes the :class:`app.upload.services.UploadService` for reuse and the
:data:`app.upload.routes.router` registered on the application's API router.
"""

from app.upload.routes import router
from app.upload.services import UploadService

__all__ = ["UploadService", "router"]
