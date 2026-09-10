"""Application History module.

Business-facing, IT-only view over the existing application lifecycle data.
Reads the same tables the rest of the system writes (applications,
documents, application_validation_history, queue_jobs, human_reviews) and
presents them as a human-readable, chronological timeline. No new audit
infrastructure is created -- this module is a read-only projection over what
already exists.

Routes are registered on the protected router; every endpoint enforces the IT
role (see ``app/auth/dependencies.require_role``), with the Employee account
inheriting access by the same single-point-superuser rule as every other IT
endpoint.
"""

from app.application_history.routes import router

__all__ = ["router"]