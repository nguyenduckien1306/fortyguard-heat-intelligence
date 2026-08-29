"""Health and readiness diagnostic routes."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Response, status

from backend.config import get_settings

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("", include_in_schema=True)
def health_overview() -> dict[str, Any]:
    """Return service health and FortyGuard configuration status."""
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "fortyguard_api_configured": settings.fortyguard_api_configured,
        "fortyguard_base_url": settings.fortyguard_base_url,
        "limits": {
            "max_history_records": settings.max_history_records,
            "max_watchlists": settings.max_watchlists,
            "max_alerts": settings.max_alerts,
            "max_queue_items": settings.max_queue_items,
        },
    }


@router.get("/live")
def liveness_check() -> dict[str, str]:
    """Liveness probe: verifies process is running and accepting requests."""
    return {"status": "alive"}


@router.get("/ready")
def readiness_check(response: Response) -> dict[str, Any]:
    """Readiness probe: verifies service configuration validity."""
    settings = get_settings()
    is_ready = True
    reason = "Application is fully configured and ready."

    if not settings.fortyguard_api_configured:
        # Service is ready to serve mock/local intelligence, but provider integration is unconfigured
        reason = "Provider API key unconfigured; running in local/demo mode."

    return {
        "status": "ready" if is_ready else "not_ready",
        "service": settings.service_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "provider_configured": settings.fortyguard_api_configured,
        "message": reason,
    }
