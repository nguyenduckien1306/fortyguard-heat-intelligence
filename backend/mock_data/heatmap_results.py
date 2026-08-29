"""
MOCK DATA — NOT LIVE FORTYGUARD DATA.

FortyGuard has not published a schema for a completed Heatmap ``result``.
These fixtures are hand-authored for local development and testing only,
so that the Phase 3 result adapter and UI components can be built and
exercised without a live FortyGuard request. Field names here (``map_data``,
``statistics``, ``metadata``, ``points``, etc.) are development conventions,
not FortyGuard-documented fields.
"""

from __future__ import annotations

from typing import Any

MOCK_RESULT_FULL: dict[str, Any] = {
    "map_data": {
        "points": [
            {"lon": -74.0170, "lat": 40.7050, "value": 31.2},
            {"lon": -74.0090, "lat": 40.7110, "value": 36.8},
            {"lon": -74.0030, "lat": 40.7180, "value": 28.4},
        ]
    },
    "statistics": {
        "avg_temp_c": 32.1,
        "max_temp_c": 36.8,
        "min_temp_c": 28.4,
        "data_points": 3,
    },
    "metadata": {
        "granularity": 100,
        "generated_by": "mock-fixture",
    },
}

MOCK_RESULT_NO_MAP_DATA: dict[str, Any] = {
    "statistics": {
        "avg_temp_c": 30.5,
        "data_points": 1,
    },
    "metadata": {
        "granularity": 100,
    },
}

MOCK_RESULT_NO_STATISTICS: dict[str, Any] = {
    "map_data": {
        "points": [
            {"lon": -74.0170, "lat": 40.7050, "value": 31.2},
        ]
    },
    "metadata": {
        "granularity": 100,
    },
}

MOCK_RESULT_EMPTY: dict[str, Any] = {}

MOCK_RESULT_MALFORMED: dict[str, Any] = {
    "map_data": "unexpected-string-shape",
    "statistics": ["not", "a", "dict"],
    "metadata": None,
}

ALL_MOCK_RESULT_FIXTURES: dict[str, dict[str, Any]] = {
    "Full result": MOCK_RESULT_FULL,
    "Missing map data": MOCK_RESULT_NO_MAP_DATA,
    "Missing statistics": MOCK_RESULT_NO_STATISTICS,
    "Empty result": MOCK_RESULT_EMPTY,
    "Malformed result": MOCK_RESULT_MALFORMED,
}
