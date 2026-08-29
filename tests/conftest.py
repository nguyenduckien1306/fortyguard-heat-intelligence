"""Shared test helpers for heatmap client tests."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from backend.api.client import FortyGuardClient
from backend.config import Settings
from backend.models.heat_intelligence import HeatIntelligenceRequest
from backend.models.heatmap import (
    DateTimeFilter,
    Feature,
    Geometry,
    HeatmapRequest,
    PolygonAoi,
)

Handler = Callable[[httpx.Request], httpx.Response]


def sample_heatmap_request() -> HeatmapRequest:
    return HeatmapRequest(
        polygon_aoi=PolygonAoi(
            type="FeatureCollection",
            features=[
                Feature(
                    type="Feature",
                    geometry=Geometry(
                        type="Polygon",
                        coordinates=[
                            [
                                [-74.0170, 40.7050],
                                [-74.0030, 40.7050],
                                [-74.0030, 40.7180],
                                [-74.0170, 40.7180],
                                [-74.0170, 40.7050],
                            ]
                        ],
                    )
                )
            ]
        ),
        date_time=DateTimeFilter(
            start_date="2024-07-15",
            start_time="14:00",
            filter_type=1,
        ),
        granularity=100,
    )


def sample_heat_intelligence_request() -> HeatIntelligenceRequest:
    return HeatIntelligenceRequest(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=32.5,
        date="2024-07-15",
        analysis=["environmental", "urban"],
    )




def make_client(
    handler: Handler,
    api_key: str = "test-key",
) -> FortyGuardClient:
    settings = Settings(
        FORTYGUARD_API_KEY=api_key,
        FORTYGUARD_BASE_URL="https://api.fortyguard.com",
    )
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://api.fortyguard.com",
        transport=transport,
        headers={"Content-Type": "application/json", "api-key": api_key},
    )
    return FortyGuardClient(settings=settings, http_client=http_client)


def submission_payload(activity_id: str = "activity-123") -> dict:
    return {
        "error": False,
        "status_code": 200,
        "message": "Heatmap Submitted Successfully",
        "data": {"activity_id": activity_id},
    }


def status_payload(
    activity_id: str = "activity-123",
    status: str = "Processing",
    result: dict | None = None,
) -> dict:
    data: dict = {"activity_id": activity_id, "status": status}
    if result is not None:
        data["result"] = result
    return {
        "error": False,
        "status_code": 200,
        "message": status,
        "data": data,
    }
