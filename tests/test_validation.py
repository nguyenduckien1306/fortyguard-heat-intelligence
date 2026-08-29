"""Comprehensive unit tests for the centralized pure validation core.

Covers boundary cases, boolean rejection, non-finite values, combination errors,
and structural GeoJSON validation without making any network requests.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
import math
from typing import Any

import pytest

from frontend.utils.heatmap import DEFAULT_POLYGON_AOI
from frontend.utils.validation import (
    ValidationResult,
    validate_analysis_categories,
    validate_date,
    validate_geojson_polygon_aoi,
    validate_granularity,
    validate_heat_intelligence_request,
    validate_heatmap_request,
    validate_latitude,
    validate_longitude,
    validate_temperature,
    validate_time,
)


# ──────────────────────────────────────────────────────────────────────────────
# Latitude Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "lat",
    [-90.0, -90, 90.0, 90, 0.0, 0, 40.7050, -45.123456],
)
def test_validate_latitude_valid(lat: Any) -> None:
    is_valid, err = validate_latitude(lat)
    assert is_valid is True
    assert err is None


@pytest.mark.parametrize(
    "lat,expected_substr",
    [
        (90.0001, "between -90° and 90°"),
        (-90.0001, "between -90° and 90°"),
        (100.0, "between -90° and 90°"),
        (-100.0, "between -90° and 90°"),
        (200.0, "between -90° and 90°"),
        (None, "required"),
        (True, "valid number"),
        (False, "valid number"),
        (math.nan, "finite number"),
        (math.inf, "finite number"),
        (-math.inf, "finite number"),
        ("abc", "valid number"),
    ],
)
def test_validate_latitude_invalid(lat: Any, expected_substr: str) -> None:
    is_valid, err = validate_latitude(lat)
    assert is_valid is False
    assert err is not None
    assert expected_substr.lower() in err.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Longitude Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "lon",
    [-180.0, -180, 180.0, 180, 0.0, 0, -74.0090, 139.6917],
)
def test_validate_longitude_valid(lon: Any) -> None:
    is_valid, err = validate_longitude(lon)
    assert is_valid is True
    assert err is None


@pytest.mark.parametrize(
    "lon,expected_substr",
    [
        (180.0001, "between -180° and 180°"),
        (-180.0001, "between -180° and 180°"),
        (200.0, "between -180° and 180°"),
        (-200.0, "between -180° and 180°"),
        (None, "required"),
        (True, "valid number"),
        (False, "valid number"),
        (math.nan, "finite number"),
        (math.inf, "finite number"),
        (-math.inf, "finite number"),
        ("xyz", "valid number"),
    ],
)
def test_validate_longitude_invalid(lon: Any, expected_substr: str) -> None:
    is_valid, err = validate_longitude(lon)
    assert is_valid is False
    assert err is not None
    assert expected_substr.lower() in err.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Temperature Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "temp",
    [-100.0, -100, 100.0, 100, 32.5, 0.0, -25.0, 50.0],
)
def test_validate_temperature_valid(temp: Any) -> None:
    is_valid, err = validate_temperature(temp)
    assert is_valid is True
    assert err is None


@pytest.mark.parametrize(
    "temp,expected_substr",
    [
        (-100.1, "between -100°C and 100°C"),
        (100.1, "between -100°C and 100°C"),
        (200.0, "between -100°C and 100°C"),
        (-150.0, "between -100°C and 100°C"),
        (None, "required"),
        (True, "valid number"),
        (False, "valid number"),
        (math.nan, "finite number"),
        (math.inf, "finite number"),
        ("hot", "valid number"),
    ],
)
def test_validate_temperature_invalid(temp: Any, expected_substr: str) -> None:
    is_valid, err = validate_temperature(temp)
    assert is_valid is False
    assert err is not None
    assert expected_substr.lower() in err.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Analysis Category Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_validate_analysis_categories_valid() -> None:
    assert validate_analysis_categories(["environmental"])[0] is True
    assert validate_analysis_categories(["environmental", "urban"])[0] is True
    assert validate_analysis_categories(["geographic", "environmental", "urban", "events", "anthropogenic"])[0] is True


@pytest.mark.parametrize(
    "categories",
    [
        [],
        None,
        ["unknown_dimension"],
        ["environmental", "invalid_dim"],
        "",
        123,
    ],
)
def test_validate_analysis_categories_invalid(categories: Any) -> None:
    is_valid, err = validate_analysis_categories(categories)
    assert is_valid is False
    assert err is not None


# ──────────────────────────────────────────────────────────────────────────────
# Date & Time Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_validate_date_valid() -> None:
    assert validate_date(date(2024, 7, 15))[0] is True
    assert validate_date("2024-07-15")[0] is True


def test_validate_date_invalid() -> None:
    assert validate_date(None)[0] is False
    assert validate_date("2024-02-30")[0] is False  # Invalid calendar date
    assert validate_date("15-07-2024")[0] is False  # Wrong format
    assert validate_date("not-a-date")[0] is False


def test_validate_time_valid() -> None:
    assert validate_time(time(14, 0))[0] is True
    assert validate_time("14:00")[0] is True
    assert validate_time("00:00")[0] is True
    assert validate_time("23:59")[0] is True


def test_validate_time_invalid() -> None:
    assert validate_time(None)[0] is False
    assert validate_time("24:00")[0] is False
    assert validate_time("12:60")[0] is False
    assert validate_time("invalid")[0] is False


def test_validate_granularity_valid() -> None:
    assert validate_granularity(100)[0] is True
    assert validate_granularity(1)[0] is True
    assert validate_granularity("50")[0] is True


def test_validate_granularity_invalid() -> None:
    assert validate_granularity(0)[0] is False
    assert validate_granularity(-5)[0] is False
    assert validate_granularity(True)[0] is False
    assert validate_granularity(False)[0] is False
    assert validate_granularity(None)[0] is False


# ──────────────────────────────────────────────────────────────────────────────
# GeoJSON AOI Structural Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_validate_geojson_polygon_aoi_valid() -> None:
    res = validate_geojson_polygon_aoi(DEFAULT_POLYGON_AOI)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validate_geojson_polygon_aoi_none_or_empty() -> None:
    res = validate_geojson_polygon_aoi(None)
    assert res.is_valid is False
    assert "required" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_invalid_json_string() -> None:
    res = validate_geojson_polygon_aoi("not valid json {")
    assert res.is_valid is False
    assert "not valid json" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_not_feature_collection() -> None:
    res = validate_geojson_polygon_aoi({"type": "Point", "coordinates": [0, 0]})
    assert res.is_valid is False
    assert "featurecollection" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_empty_features() -> None:
    res = validate_geojson_polygon_aoi({"type": "FeatureCollection", "features": []})
    assert res.is_valid is False
    assert "at least one feature" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_non_polygon_geometry() -> None:
    bad_aoi = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            }
        ],
    }
    res = validate_geojson_polygon_aoi(bad_aoi)
    assert res.is_valid is False
    assert "only 'polygon' is supported" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_ring_not_closed() -> None:
    bad_aoi = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-74.0, 40.0], [-74.0, 41.0], [-73.0, 41.0], [-73.0, 40.0]]  # Open ring
                    ],
                },
            }
        ],
    }
    res = validate_geojson_polygon_aoi(bad_aoi)
    assert res.is_valid is False
    assert "not closed" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_ring_too_short() -> None:
    bad_aoi = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-74.0, 40.0], [-74.0, 41.0], [-74.0, 40.0]]],  # 3 points
                },
            }
        ],
    }
    res = validate_geojson_polygon_aoi(bad_aoi)
    assert res.is_valid is False
    assert "at least 4" in res.errors[0].lower()


def test_validate_geojson_polygon_aoi_out_of_bounds_coordinates() -> None:
    # Latitude 100 is out of bounds
    bad_aoi = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-74.0, 100.0],  # Lat > 90
                            [-74.0, 41.0],
                            [-73.0, 41.0],
                            [-73.0, 100.0],
                            [-74.0, 100.0],
                        ]
                    ],
                },
            }
        ],
    }
    res = validate_geojson_polygon_aoi(bad_aoi)
    assert res.is_valid is False
    assert "latitude" in res.errors[0].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Aggregated Heat Intelligence Request Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_heat_intelligence_request_all_valid() -> None:
    res = validate_heat_intelligence_request(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=32.5,
        date_val=date(2024, 7, 15),
        categories=["environmental", "urban"],
    )
    assert res.is_valid is True
    assert len(res.errors) == 0
    assert len(res.field_errors) == 0


def test_heat_intelligence_out_of_range_coordinates_are_not_ready() -> None:
    """Regression test for the manual discovery: 100.0 / 200.0 must fail validation."""
    res = validate_heat_intelligence_request(
        latitude=100.0,
        longitude=200.0,
        temperature=32.5,
        date_val=date(2024, 7, 15),
        categories=["geographic"],
    )
    assert res.is_valid is False
    assert "latitude" in res.field_errors
    assert "longitude" in res.field_errors
    assert len(res.errors) == 2


def test_heat_intelligence_aggregates_multiple_errors() -> None:
    """Verifies that validator aggregates errors rather than stopping at the first failure."""
    res = validate_heat_intelligence_request(
        latitude=100.0,  # invalid
        longitude=200.0,  # invalid
        temperature=150.0,  # invalid
        date_val=None,  # invalid
        categories=[],  # invalid
    )
    assert res.is_valid is False
    assert len(res.errors) == 5
    assert "latitude" in res.field_errors
    assert "longitude" in res.field_errors
    assert "temperature" in res.field_errors
    assert "date" in res.field_errors
    assert "analysis" in res.field_errors


def test_heat_intelligence_temperature_warning() -> None:
    """Verify non-blocking warnings (e.g. >55°C) are added without blocking valid submission."""
    res = validate_heat_intelligence_request(
        latitude=40.7050,
        longitude=-74.0090,
        temperature=58.0,  # exceptionally high but within 100°C limit
        date_val=date(2024, 7, 15),
        categories=["environmental"],
    )
    assert res.is_valid is True  # Warning does not block submission
    assert len(res.warnings) == 1
    assert "high" in res.warnings[0].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Aggregated Heatmap Request Validation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_heatmap_request_all_valid() -> None:
    res = validate_heatmap_request(
        polygon_aoi=DEFAULT_POLYGON_AOI,
        date_val=date(2024, 7, 15),
        time_val=time(14, 0),
        granularity=100,
        location_label="Downtown AOI",
    )
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_heatmap_request_optional_label_empty() -> None:
    res = validate_heatmap_request(
        polygon_aoi=DEFAULT_POLYGON_AOI,
        date_val=date(2024, 7, 15),
        time_val=time(14, 0),
        granularity=100,
        location_label="",  # Optional
    )
    assert res.is_valid is True


def test_heatmap_request_invalid_parameters() -> None:
    res = validate_heatmap_request(
        polygon_aoi=DEFAULT_POLYGON_AOI,
        date_val=None,
        time_val=None,
        granularity=0,
    )
    assert res.is_valid is False
    assert "date" in res.field_errors
    assert "time" in res.field_errors
    assert "granularity" in res.field_errors
