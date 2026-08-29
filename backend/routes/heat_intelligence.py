"""Heat Intelligence API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.api.exceptions import FortyGuardClientError
from backend.models.common import ActivityStatusResponse
from backend.models.heat_intelligence import (
    HeatIntelligenceRequest,
    HeatIntelligenceSubmitAPIResponse,
)
from backend.services.heat_intelligence_service import HeatIntelligenceService

router = APIRouter(prefix="/api/v1/heat-intelligence", tags=["heat-intelligence"])


def get_heat_intelligence_service() -> HeatIntelligenceService:
    return HeatIntelligenceService()


@router.post("/", response_model=HeatIntelligenceSubmitAPIResponse)
def submit_heat_intelligence(
    request: HeatIntelligenceRequest,
    service: HeatIntelligenceService = Depends(get_heat_intelligence_service),
) -> HeatIntelligenceSubmitAPIResponse:
    """Submit a Heat Intelligence request to FortyGuard via the backend client."""
    try:
        submission = service.submit_heat_intelligence(request)
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    return HeatIntelligenceSubmitAPIResponse(activity_id=submission.activity_id)


@router.get("/status/{activity_id}", response_model=ActivityStatusResponse)
def get_heat_intelligence_status(
    activity_id: str,
    service: HeatIntelligenceService = Depends(get_heat_intelligence_service),
) -> ActivityStatusResponse:
    """Return the current FortyGuard activity status for a Heat Intelligence job."""
    try:
        return service.get_heat_intelligence_status(activity_id)
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.get("/status/{activity_id}/poll", response_model=ActivityStatusResponse)
def poll_heat_intelligence_status(
    activity_id: str,
    max_attempts: int = Query(default=30, ge=1),
    poll_interval_seconds: float = Query(default=2.0, ge=0),
    service: HeatIntelligenceService = Depends(get_heat_intelligence_service),
) -> ActivityStatusResponse:
    """Poll a Heat Intelligence task using bounded polling."""
    try:
        return service.poll_heat_intelligence(
            activity_id,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.get("/report/{activity_id}")
def download_heat_intelligence_report(
    activity_id: str,
    service: HeatIntelligenceService = Depends(get_heat_intelligence_service),
) -> Response:
    """Download the completed Heat Intelligence PDF report.

    Proxies the signed S3 download through the backend so that
    temporary signed URLs are never exposed to the frontend.
    """
    try:
        pdf_bytes = service.fetch_report(activity_id)
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="heat_intelligence_report_{activity_id}.pdf"',
        },
    )
