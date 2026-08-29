"""
MOCK DATA — NOT LIVE FORTYGUARD DATA.

Re-exports the canonical mock Heatmap result fixtures from
``backend.mock_data.heatmap_results`` so tests can import them from a
conventional ``tests/fixtures`` location. The frontend dev-preview toggle
uses the same canonical module directly.
"""

from backend.mock_data.heatmap_results import (
    ALL_MOCK_RESULT_FIXTURES,
    MOCK_RESULT_EMPTY,
    MOCK_RESULT_FULL,
    MOCK_RESULT_MALFORMED,
    MOCK_RESULT_NO_MAP_DATA,
    MOCK_RESULT_NO_STATISTICS,
)

__all__ = [
    "ALL_MOCK_RESULT_FIXTURES",
    "MOCK_RESULT_EMPTY",
    "MOCK_RESULT_FULL",
    "MOCK_RESULT_MALFORMED",
    "MOCK_RESULT_NO_MAP_DATA",
    "MOCK_RESULT_NO_STATISTICS",
]
