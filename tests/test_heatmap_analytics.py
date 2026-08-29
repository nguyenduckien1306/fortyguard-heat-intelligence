"""Tests for derived heatmap analytics and data quality utilities."""

from __future__ import annotations

from frontend.utils.heatmap_analytics import compute_tile_metrics, get_heatmap_data_quality_report


def test_compute_tile_metrics_normal() -> None:
    map_data = {
        "type": "FeatureCollection",
        "features": [
            {"id": "0", "properties": {"tile_id": 0, "average_temperature": 30.0}},
            {"id": "1", "properties": {"tile_id": 1, "average_temperature": 35.0}},
            {"id": "2", "properties": {"tile_id": 2, "average_temperature": 25.0}},
        ],
    }
    metrics = compute_tile_metrics(map_data)
    assert metrics["total_tiles"] == 3
    assert metrics["valid_tiles_count"] == 3
    assert metrics["missing_tiles_count"] == 0
    assert metrics["min_temp"] == 25.0
    assert metrics["max_temp"] == 35.0
    assert metrics["mean_temp"] == 30.0
    assert metrics["temp_spread"] == 10.0
    assert metrics["hottest_tile"] == {"tile_id": 1, "temperature": 35.0}
    assert metrics["coolest_tile"] == {"tile_id": 2, "temperature": 25.0}


def test_compute_tile_metrics_partial_missing_data() -> None:
    map_data = {
        "type": "FeatureCollection",
        "features": [
            {"id": "0", "properties": {"tile_id": 0, "average_temperature": 32.0}},
            {"id": "1", "properties": {"tile_id": 1, "average_temperature": None}},
            {"id": "2", "properties": {"tile_id": 2}},  # missing key
        ],
    }
    metrics = compute_tile_metrics(map_data)
    assert metrics["total_tiles"] == 3
    assert metrics["valid_tiles_count"] == 1
    assert metrics["missing_tiles_count"] == 2
    assert metrics["min_temp"] == 32.0
    assert metrics["max_temp"] == 32.0
    assert metrics["temp_spread"] == 0.0


def test_compute_tile_metrics_negative_and_uniform_temperatures() -> None:
    # Negative temperatures
    map_neg = {
        "type": "FeatureCollection",
        "features": [
            {"properties": {"tile_id": "A", "average_temperature": -10.5}},
            {"properties": {"tile_id": "B", "average_temperature": -2.5}},
        ],
    }
    metrics_neg = compute_tile_metrics(map_neg)
    assert metrics_neg["min_temp"] == -10.5
    assert metrics_neg["max_temp"] == -2.5
    assert metrics_neg["temp_spread"] == 8.0

    # Uniform temperatures
    map_uni = {
        "type": "FeatureCollection",
        "features": [
            {"properties": {"tile_id": "1", "average_temperature": 22.0}},
            {"properties": {"tile_id": "2", "average_temperature": 22.0}},
        ],
    }
    metrics_uni = compute_tile_metrics(map_uni)
    assert metrics_uni["min_temp"] == 22.0
    assert metrics_uni["max_temp"] == 22.0
    assert metrics_uni["temp_spread"] == 0.0


def test_compute_tile_metrics_empty_or_invalid() -> None:
    assert compute_tile_metrics(None)["total_tiles"] == 0
    assert compute_tile_metrics({})["total_tiles"] == 0
    assert compute_tile_metrics({"type": "FeatureCollection", "features": []})["total_tiles"] == 0


def test_get_heatmap_data_quality_report() -> None:
    # Complete
    map_complete = {
        "type": "FeatureCollection",
        "features": [{"properties": {"average_temperature": 20.0}}],
    }
    q_complete = get_heatmap_data_quality_report(map_complete)
    assert q_complete["is_valid_geojson"] is True
    assert q_complete["is_complete"] is True
    assert q_complete["missing_tiles"] == 0

    # Incomplete
    map_incomplete = {
        "type": "FeatureCollection",
        "features": [
            {"properties": {"average_temperature": 20.0}},
            {"properties": {"average_temperature": None}},
        ],
    }
    q_incomplete = get_heatmap_data_quality_report(map_incomplete)
    assert q_incomplete["is_complete"] is False
    assert q_incomplete["missing_tiles"] == 1


def test_compute_tile_metrics_single_tile() -> None:
    map_single = {
        "type": "FeatureCollection",
        "features": [{"properties": {"tile_id": 99, "average_temperature": 28.75}}],
    }
    metrics = compute_tile_metrics(map_single)
    assert metrics["total_tiles"] == 1
    assert metrics["valid_tiles_count"] == 1
    assert metrics["min_temp"] == 28.75
    assert metrics["max_temp"] == 28.75
    assert metrics["mean_temp"] == 28.75
    assert metrics["temp_spread"] == 0.0
    assert metrics["hottest_tile"] == {"tile_id": 99, "temperature": 28.75}
    assert metrics["coolest_tile"] == {"tile_id": 99, "temperature": 28.75}


def test_get_heatmap_data_quality_report_empty_features() -> None:
    rep = get_heatmap_data_quality_report({"type": "FeatureCollection", "features": []})
    assert rep["total_tiles"] == 0
    assert rep["is_complete"] is False
    assert any("No spatial polygon tiles" in n for n in rep["notes"])
