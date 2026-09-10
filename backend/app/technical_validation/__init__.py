"""Technical file validation package.

Exposes the service and HTTP router for validating the technical quality of
uploaded documents (accessibility, format, PDF/image structure, blur, rotation
and readability) without inspecting their contents.
"""

from app.technical_validation.routes import router
from app.technical_validation.services import TechnicalValidationService

__all__ = ["TechnicalValidationService", "router"]
