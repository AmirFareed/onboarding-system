"""API package.

Aggregates every versioned router into a single ``api_router`` that the FastAPI
application mounts under the configured API prefix. Future feature routers
(upload, validation, etc.) are registered on ``protected_router`` below so the
application factory does not need to change when new endpoints are added, and
so a new router is authenticated by default.

Every route requires a valid session (``Depends(get_current_user)``, applied
once here rather than per-router) except ``health`` and the ``auth`` module
itself. Applying this per-router individually is what shipped 13 of 14 modules
with no auth enforcement at all in the first place -- see CONTEXT.md's
2026-08-14 entries -- so it is applied globally, with an explicit allowlist
for the two routers that must stay reachable pre-session, rather than opt-in
per module.
"""

from fastapi import APIRouter, Depends

from app.api.health import router as health_router
from app.application_history.routes import router as application_history_router
from app.auth.dependencies import get_current_user
from app.auth.routes import router as auth_router
from app.bulk_queue.routes import router as bulk_queue_router
from app.completeness.routes import router as completeness_router
from app.confidence.routes import router as confidence_router
from app.continuous_learning.routes import router as continuous_learning_router
from app.document_analysis.routes import router as document_analysis_router
from app.document_processing.routes import router as document_processing_router
from app.feedback.routes import router as feedback_router
from app.human_verification.routes import router as human_verification_router
from app.normalization.routes import router as normalization_router
from app.operator_workflow.routes import router as operator_workflow_router
from app.performance.routes import router as performance_router
from app.reports.routes import router as reports_router
from app.rule_engine.routes import router as rule_engine_router
from app.system_logs.routes import router as system_logs_router
from app.technical_validation.routes import router as technical_validation_router
from app.upload.routes import router as upload_router

api_router = APIRouter()

# Unauthenticated: health checks, and the auth module itself. Login must be
# reachable pre-session; /me, /refresh and /logout each validate their own
# cookie inline rather than through get_current_user, since /refresh in
# particular must still work when the access-token cookie has already
# expired (that's the token it's replacing).
api_router.include_router(health_router)
api_router.include_router(auth_router)

# Everything else requires a valid session.
protected_router = APIRouter(dependencies=[Depends(get_current_user)])
# Application History first: its literal /applications/history route must be
# matched before upload_router's dynamic /applications/{application_id}.
protected_router.include_router(application_history_router)
protected_router.include_router(bulk_queue_router)
protected_router.include_router(upload_router)
protected_router.include_router(completeness_router)
protected_router.include_router(technical_validation_router)
protected_router.include_router(document_processing_router)
protected_router.include_router(document_analysis_router)
protected_router.include_router(confidence_router)
protected_router.include_router(normalization_router)
protected_router.include_router(rule_engine_router)
protected_router.include_router(reports_router)
protected_router.include_router(human_verification_router)
protected_router.include_router(feedback_router)
protected_router.include_router(continuous_learning_router)
protected_router.include_router(operator_workflow_router)
protected_router.include_router(system_logs_router)
protected_router.include_router(performance_router)

api_router.include_router(protected_router)

__all__ = ["api_router"]
