"""Derived analytics and data quality utilities for Heatmap results.

All calculations are derived locally and deterministically from confirmed
FortyGuard GeoJSON tile features without modifying or inventing provider fields.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def compute_tile_metrics(
    map_data: Any,
    property_key: str = "average_temperature",
) -> dict[str, Any]:
    """
    Compute derived summary metrics and temperature extremes from GeoJSON features.

    Returns a dict containing:
    - total_tiles: int
    - valid_tiles_count: int
    - missing_tiles_count: int
    - min_temp: float | None
    - max_temp: float | None
    - mean_temp: float | None
    - temp_spread: float | None (max - min)
    - hottest_tile: dict(tile_id, temperature) | None
    - coolest_tile: dict(tile_id, temperature) | None
    """
    if not isinstance(map_data, Mapping):
        return _empty_tile_metrics()

    features = map_data.get("features")
    if not isinstance(features, list) or not features:
        return _empty_tile_metrics()

    total_tiles = len(features)
    valid_values: list[tuple[Any, float]] = []  # (tile_id, temp)

    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        props = feature.get("properties")
        if not isinstance(props, Mapping):
            continue

        tile_id = props.get("tile_id", feature.get("id", "N/A"))
        val = props.get(property_key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            valid_values.append((tile_id, float(val)))

    valid_count = len(valid_values)
    missing_count = total_tiles - valid_count

    if not valid_values:
        return {
            "total_tiles": total_tiles,
            "valid_tiles_count": 0,
            "missing_tiles_count": missing_count,
            "min_temp": None,
            "max_temp": None,
            "mean_temp": None,
            "temp_spread": None,
            "hottest_tile": None,
            "coolest_tile": None,
        }

    # Sort to find min, max, hottest, coolest
    sorted_by_temp = sorted(valid_values, key=lambda x: x[1])
    coolest_tile = {"tile_id": sorted_by_temp[0][0], "temperature": sorted_by_temp[0][1]}
    hottest_tile = {"tile_id": sorted_by_temp[-1][0], "temperature": sorted_by_temp[-1][1]}

    temps = [t for _, t in valid_values]
    min_temp = min(temps)
    max_temp = max(temps)
    mean_temp = sum(temps) / len(temps)
    temp_spread = max_temp - min_temp

    return {
        "total_tiles": total_tiles,
        "valid_tiles_count": valid_count,
        "missing_tiles_count": missing_count,
        "min_temp": round(min_temp, 2),
        "max_temp": round(max_temp, 2),
        "mean_temp": round(mean_temp, 2),
        "temp_spread": round(temp_spread, 2),
        "hottest_tile": hottest_tile,
        "coolest_tile": coolest_tile,
    }


def _empty_tile_metrics() -> dict[str, Any]:
    return {
        "total_tiles": 0,
        "valid_tiles_count": 0,
        "missing_tiles_count": 0,
        "min_temp": None,
        "max_temp": None,
        "mean_temp": None,
        "temp_spread": None,
        "hottest_tile": None,
        "coolest_tile": None,
    }


def get_heatmap_data_quality_report(map_data: Any) -> dict[str, Any]:
    """
    Generate a transparent data quality assessment for the received GeoJSON map data.
    """
    metrics = compute_tile_metrics(map_data)
    total = metrics["total_tiles"]
    valid = metrics["valid_tiles_count"]
    missing = metrics["missing_tiles_count"]

    is_valid_geojson = isinstance(map_data, Mapping) and map_data.get("type") == "FeatureCollection"
    is_complete = total > 0 and missing == 0

    notes: list[str] = []
    if not is_valid_geojson:
        notes.append("Map data is not a standard FeatureCollection.")
    elif total == 0:
        notes.append("No spatial polygon tiles present in map payload.")
    elif missing > 0:
        notes.append(f"{missing} of {total} tiles are missing numeric temperature values.")
    else:
        notes.append(f"Complete temperature coverage across all {total} tiles.")

    return {
        "is_valid_geojson": is_valid_geojson,
        "total_tiles": total,
        "valid_tiles": valid,
        "missing_tiles": missing,
        "is_complete": is_complete,
        "notes": notes,
    }
