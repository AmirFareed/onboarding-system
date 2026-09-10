"""Validation report module.

Aggregates the results persisted by the earlier pipeline stages into a
structured, printable report for employee review. Read-only: it never runs a
rule, never runs a detection and never writes to the database.
"""

from app.reports.constants import REPORT_VERSION
from app.reports.routes import router
from app.reports.services import ValidationReportService

__all__ = ["REPORT_VERSION", "ValidationReportService", "router"]
