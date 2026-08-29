"""Heatmap API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.exceptions import FortyGuardClientError
from backend.models.common import ActivityStatusResponse
from backend.models.heatmap import HeatmapRequest, HeatmapSubmitAPIResponse
from backend.services.heatmap_service import HeatmapService

router = APIRouter(prefix="/api/v1/heatmap", tags=["heatmap"])


def get_heatmap_service() -> HeatmapService:
    return HeatmapService()


@router.post("/", response_model=HeatmapSubmitAPIResponse)
def submit_heatmap(
    request: HeatmapRequest,
    service: HeatmapService = Depends(get_heatmap_service),
) -> HeatmapSubmitAPIResponse:
    """Submit a heatmap request to FortyGuard via the backend client."""
    try:
        submission = service.submit_heatmap(request)
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

    return HeatmapSubmitAPIResponse(activity_id=submission.activity_id)


@router.get("/status/{activity_id}", response_model=ActivityStatusResponse)
def get_heatmap_status(
    activity_id: str,
    service: HeatmapService = Depends(get_heatmap_service),
) -> ActivityStatusResponse:
    """Return the current FortyGuard activity status for a heatmap job."""
    try:
        return service.get_heatmap_status(activity_id)
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc


@router.get("/status/{activity_id}/poll", response_model=ActivityStatusResponse)
def poll_heatmap_status(
    activity_id: str,
    max_attempts: int = Query(default=30, ge=1),
    poll_interval_seconds: float = Query(default=2.0, ge=0),
    service: HeatmapService = Depends(get_heatmap_service),
) -> ActivityStatusResponse:
    """Poll a heatmap task using the service's bounded polling behavior."""
    try:
        return service.poll_heatmap(
            activity_id,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )
    except FortyGuardClientError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
