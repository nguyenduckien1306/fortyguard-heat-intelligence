"""Tests for the human-friendly polygon coordinate builder and GeoJSON generation."""

from __future__ import annotations

import pytest

from frontend.utils.heatmap import (
    DEFAULT_POLYGON_POINTS,
    build_polygon_geojson_from_points,
)
from frontend.utils.validation import validate_geojson_polygon_aoi


def test_build_polygon_geojson_valid_4_points() -> None:
    """Builds valid GeoJSON with 4 input points, auto-closing to 5 positions in [lon, lat] format."""
    points = [
        {"lat": 40.7050, "lon": -74.0170},
        {"lat": 40.7050, "lon": -74.0030},
        {"lat": 40.7180, "lon": -74.0030},
        {"lat": 40.7180, "lon": -74.0170},
    ]

    geojson = build_polygon_geojson_from_points(points)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1

    feature = geojson["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    coords = feature["geometry"]["coordinates"][0]

    # Must be 5 positions (4 points + 1 closure point)
    assert len(coords) == 5
    # First position must match last
    assert coords[0] == coords[-1]

    # Verify GeoJSON order: [longitude, latitude]
    assert coords[0] == [-74.0170, 40.7050]
    assert coords[1] == [-74.0030, 40.7050]
    assert coords[2] == [-74.0030, 40.7180]
    assert coords[3] == [-74.0170, 40.7180]

    # Verify passes centralized GeoJSON validation
    val_res = validate_geojson_polygon_aoi(geojson)
    assert val_res.is_valid is True
    assert len(val_res.errors) == 0


def test_build_polygon_geojson_valid_3_points() -> None:
    """Triangle (3 points) auto-closes to 4 positions and passes validation."""
    points = [
        {"lat": 40.7000, "lon": -74.0100},
        {"lat": 40.7100, "lon": -74.0000},
        {"lat": 40.7000, "lon": -73.9900},
    ]

    geojson = build_polygon_geojson_from_points(points)
    coords = geojson["features"][0]["geometry"]["coordinates"][0]

    assert len(coords) == 4
    assert coords[0] == coords[-1]
    assert coords[0] == [-74.0100, 40.7000]

    val_res = validate_geojson_polygon_aoi(geojson)
    assert val_res.is_valid is True


def test_build_polygon_geojson_already_closed_ring() -> None:
    """If points already contain closing duplicate point, does not add redundant 6th position."""
    points = [
        {"lat": 40.7000, "lon": -74.0100},
        {"lat": 40.7100, "lon": -74.0100},
        {"lat": 40.7100, "lon": -73.9900},
        {"lat": 40.7000, "lon": -74.0100},
    ]

    geojson = build_polygon_geojson_from_points(points)
    coords = geojson["features"][0]["geometry"]["coordinates"][0]
    assert len(coords) == 4
    assert coords[0] == coords[-1]


def test_build_polygon_geojson_accepts_tuples() -> None:
    """Accepts sequence of (lat, lon) tuples."""
    points = [
        (40.7050, -74.0170),
        (40.7050, -74.0030),
        (40.7180, -74.0030),
    ]
    geojson = build_polygon_geojson_from_points(points)
    coords = geojson["features"][0]["geometry"]["coordinates"][0]
    assert len(coords) == 4
    assert coords[0] == [-74.0170, 40.7050]


def test_build_polygon_geojson_fewer_than_3_points_raises() -> None:
    """Fewer than 3 points raises ValueError."""
    with pytest.raises(ValueError, match="at least 3 points"):
        build_polygon_geojson_from_points([{"lat": 40.7, "lon": -74.0}])

    with pytest.raises(ValueError, match="at least 3 points"):
        build_polygon_geojson_from_points([
            {"lat": 40.7, "lon": -74.0},
            {"lat": 40.8, "lon": -74.0},
        ])


def test_default_polygon_points_constant_is_valid() -> None:
    """DEFAULT_POLYGON_POINTS produces a valid GeoJSON FeatureCollection."""
    geojson = build_polygon_geojson_from_points(DEFAULT_POLYGON_POINTS)
    val_res = validate_geojson_polygon_aoi(geojson)
    assert val_res.is_valid is True
