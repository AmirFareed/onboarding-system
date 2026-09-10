"""Repository facade for the feedback module.

Re-exports the persistence repositories the feedback service needs so the
service depends on this module's public surface instead of importing the
database layer directly. The module is read-mostly: the only repository used is
``FeedbackRepository``, which reads, filters, counts and aggregates the dataset
recorded by earlier phases.
"""

from app.database.repositories.feedback_repository import FeedbackRepository

__all__ = ["FeedbackRepository"]
