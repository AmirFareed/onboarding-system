"""Document completeness verification module.

Exposes the :class:`app.completeness.services.CompletenessService` for reuse and
the :data:`app.completeness.routes.router` registered on the application's API
router.
"""

from app.completeness.routes import router
from app.completeness.services import CompletenessService

__all__ = ["CompletenessService", "router"]
