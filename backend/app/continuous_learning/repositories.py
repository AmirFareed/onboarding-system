"""Repository facade for the continuous learning module.

Re-exports the persistence repositories the continuous learning service needs
so the service depends on this module's public surface instead of importing the
database layer directly. The module is read-only: it reuses the existing
``FeedbackRepository`` to read the verified feedback recorded by earlier
phases. No new table, no new repository and no modification of completed
modules is required.
"""

from app.database.repositories.feedback_repository import FeedbackRepository

__all__ = ["FeedbackRepository"]
