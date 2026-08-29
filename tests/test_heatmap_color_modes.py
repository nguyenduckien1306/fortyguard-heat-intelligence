"""Tests for user-controlled visualization color modes (average, min, max temperature)."""

from __future__ import annotations

from frontend.utils.colors import compute_temperature_bounds
from frontend.utils.heatmap import build_temperature_colored_geojson


_SAMPLE_TILES = {
    "type": "FeatureCollection",
    "features": [
        {
            "id": "0",
            "type": "Feature",
            "properties": {
                "tile_id": 0,
                "average_temperature": 30.0,
                "min_temperature": 28.0,
                "max_temperature": 32.0,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
        },
        {
            "id": "1",
            "type": "Feature",
            "properties": {
                "tile_id": 1,
                "average_temperature": 35.0,
                "min_temperature": 33.0,
                "max_temperature": 38.0,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]],
            },
        },
    ],
}


def test_color_by_average_temperature() -> None:
    bounds = compute_temperature_bounds(_SAMPLE_TILES["features"], property_key="average_temperature")
    assert bounds == (30.0, 35.0)

    colored = build_temperature_colored_geojson(_SAMPLE_TILES, property_key="average_temperature")
    f0_color = colored["features"][0]["properties"]["fill_color"]
    f1_color = colored["features"][1]["properties"]["fill_color"]

    # f0 is minimum (cool blue/cyan), f1 is maximum (deep red)
    assert f0_color != f1_color
    assert len(f0_color) == 4
    assert len(f1_color) == 4


def test_color_by_min_temperature() -> None:
    bounds = compute_temperature_bounds(_SAMPLE_TILES["features"], property_key="min_temperature")
    assert bounds == (28.0, 33.0)

    colored = build_temperature_colored_geojson(_SAMPLE_TILES, property_key="min_temperature")
    props0 = colored["features"][0]["properties"]
    assert "fill_color" in props0
    assert props0["min_temperature_str"] == "28.00 °C"


def test_color_by_max_temperature() -> None:
    bounds = compute_temperature_bounds(_SAMPLE_TILES["features"], property_key="max_temperature")
    assert bounds == (32.0, 38.0)

    colored = build_temperature_colored_geojson(_SAMPLE_TILES, property_key="max_temperature")
    props1 = colored["features"][1]["properties"]
    assert props1["max_temperature_str"] == "38.00 °C"


def test_color_mode_non_mutating() -> None:
    # Ensure source collection remains untouched
    assert "fill_color" not in _SAMPLE_TILES["features"][0]["properties"]
    _ = build_temperature_colored_geojson(_SAMPLE_TILES, property_key="max_temperature")
    assert "fill_color" not in _SAMPLE_TILES["features"][0]["properties"]
