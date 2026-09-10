"""IT system log module.

Read-only operational audit API for the IT role: searchable, filterable,
paginated access to the shared ``audit_logs`` table so IT can trace the full
history of an application and the whole system. Never exposes raw document
contents or extracted PII -- only the audit-oriented fields already recorded
by each action.
"""

from app.system_logs.routes import router

__all__ = ["router"]