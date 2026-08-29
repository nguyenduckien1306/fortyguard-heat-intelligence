"""Tests for the internal completed-Heatmap result adapter."""

from backend.models.heatmap_result import parse_heatmap_result
from tests.fixtures.heatmap_results import (
    MOCK_RESULT_EMPTY,
    MOCK_RESULT_FULL,
    MOCK_RESULT_MALFORMED,
    MOCK_RESULT_NO_MAP_DATA,
    MOCK_RESULT_NO_STATISTICS,
)


def test_parse_heatmap_result_returns_none_for_no_result() -> None:
    assert parse_heatmap_result(None) is None


def test_parse_heatmap_result_extracts_full_result() -> None:
    parsed = parse_heatmap_result(MOCK_RESULT_FULL)

    assert parsed is not None
    assert parsed.map_data == MOCK_RESULT_FULL["map_data"]
    assert parsed.statistics == MOCK_RESULT_FULL["statistics"]
    assert parsed.metadata == MOCK_RESULT_FULL["metadata"]
    assert parsed.raw == MOCK_RESULT_FULL


def test_parse_heatmap_result_missing_map_data() -> None:
    parsed = parse_heatmap_result(MOCK_RESULT_NO_MAP_DATA)

    assert parsed is not None
    assert parsed.map_data is None
    assert parsed.statistics == MOCK_RESULT_NO_MAP_DATA["statistics"]


def test_parse_heatmap_result_missing_statistics() -> None:
    parsed = parse_heatmap_result(MOCK_RESULT_NO_STATISTICS)

    assert parsed is not None
    assert parsed.statistics is None
    assert parsed.map_data == MOCK_RESULT_NO_STATISTICS["map_data"]


def test_parse_heatmap_result_empty_result() -> None:
    parsed = parse_heatmap_result(MOCK_RESULT_EMPTY)

    assert parsed is not None
    assert parsed.map_data is None
    assert parsed.statistics is None
    assert parsed.metadata is None
    assert parsed.raw == {}


def test_parse_heatmap_result_malformed_sections_are_dropped_not_guessed() -> None:
    parsed = parse_heatmap_result(MOCK_RESULT_MALFORMED)

    assert parsed is not None
    # statistics was a list, not a dict -> treated as absent rather than coerced
    assert parsed.statistics is None
    # map_data is passed through untouched for the UI to fall back on
    assert parsed.map_data == "unexpected-string-shape"
    assert parsed.metadata is None
    assert parsed.raw == MOCK_RESULT_MALFORMED


def test_parse_heatmap_result_accepts_stats_alias() -> None:
    parsed = parse_heatmap_result({"stats": {"avg_temp_c": 10}})

    assert parsed is not None
    assert parsed.statistics == {"avg_temp_c": 10}
