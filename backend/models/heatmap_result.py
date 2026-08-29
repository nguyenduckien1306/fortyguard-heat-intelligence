"""Internal adapter for interpreting a completed Heatmap task's ``result`` payload.

FortyGuard has not published written documentation for the shape of a
completed Heatmap ``result`` (``ActivityStatusResponse.result`` is a bare
``dict[str, Any] | None``). A Phase 4 live capture confirmed one real
example: ``map_data`` is a GeoJSON ``FeatureCollection`` of Polygon tiles,
and statistics are under ``stats_data`` (not ``statistics``/``stats`` —
those were Phase 3 guesses, kept here only as harmless fallbacks in case a
future response uses them). No ``metadata`` key was present in that real
response. This module still treats the shape as generally unknown: it
extracts known-looking sections defensively without inventing fields, and
always preserves the original payload on ``raw`` as a fallback.

See backend/mock_data/heatmap_results_real.py for the captured example.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HeatmapResult(BaseModel):
    """Best-effort internal view of a completed Heatmap result."""

    map_data: Any | None = None
    statistics: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    raw: dict[str, Any]


def parse_heatmap_result(result: dict[str, Any] | None) -> HeatmapResult | None:
    """
    Build a :class:`HeatmapResult` from a raw completed-task ``result`` dict.

    Returns ``None`` when there is no result at all. Unknown or malformed
    sections are dropped rather than guessed at; ``raw`` always keeps the
    untouched payload for a safe fallback display.
    """
    if result is None:
        return None

    map_data = result.get("map_data")

    statistics: dict[str, Any] | None = None
    for key in ("stats_data", "statistics", "stats"):
        candidate = result.get(key)
        if isinstance(candidate, dict):
            statistics = candidate
            break

    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        metadata = None

    return HeatmapResult(
        map_data=map_data,
        statistics=statistics,
        metadata=metadata,
        raw=result,
    )
