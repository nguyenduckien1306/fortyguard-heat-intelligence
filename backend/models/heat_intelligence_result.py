"""Internal adapter for interpreting a completed Heat Intelligence task's ``result`` payload.

Confirmed FortyGuard Schema:
- Completed result structure: `{"download_link": "https://..."}`
- `download_link` contains a temporary signed URL to download the full Heat Intelligence Report (PDF).
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class HeatIntelligenceResult(BaseModel):
    """Internal model for a completed Heat Intelligence result."""

    download_link: str | None = None
    data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    raw: dict[str, Any]


def parse_heat_intelligence_result(result: dict[str, Any] | None) -> HeatIntelligenceResult | None:
    """
    Build a :class:`HeatIntelligenceResult` from a raw completed-task ``result`` dict.

    Extracts ``download_link`` directly as confirmed from the FortyGuard API,
    while preserving untouched payload on ``raw``.
    """
    if result is None:
        return None

    download_link = result.get("download_link")
    if not isinstance(download_link, str) or not download_link.strip():
        download_link = None

    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        metadata = None

    data = result.get("data")
    if not isinstance(data, dict):
        data = None

    return HeatIntelligenceResult(
        download_link=download_link,
        data=data,
        metadata=metadata,
        raw=result,
    )
