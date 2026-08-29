"""Pure helpers for building and validating a documented heatmap request."""

from __future__ import annotations

import json
from datetime import date, time
from typing import Any, Mapping

from pydantic import ValidationError

from backend.models.heatmap import DateTimeFilter, HeatmapRequest, PolygonAoi

DEFAULT_POLYGON_AOI: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-74.0170, 40.7050],
                        [-74.0030, 40.7050],
                        [-74.0030, 40.7180],
                        [-74.0170, 40.7180],
                        [-74.0170, 40.7050],
                    ]
                ],
            },
        }
    ],
}

DEFAULT_POLYGON_POINTS: list[dict[str, float]] = [
    {"lat": 40.7050, "lon": -74.0170},
    {"lat": 40.7050, "lon": -74.0030},
    {"lat": 40.7180, "lon": -74.0030},
    {"lat": 40.7180, "lon": -74.0170},
]


def build_polygon_geojson_from_points(
    points: Any,
) -> dict[str, Any]:
    """Construct a GeoJSON Polygon FeatureCollection from a sequence of point coordinates.

    Points can be dictionaries (e.g. ``{'lat': ..., 'lon': ...}``) or (lat, lon) sequences.
    Preserves GeoJSON coordinate ordering internally: ``[longitude, latitude]``.
    Automatically closes the polygon ring by appending the first vertex if needed.
    """
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise ValueError("Polygon requires at least 3 points.")

    ring: list[list[float]] = []
    for pt in points:
        if isinstance(pt, Mapping):
            lat = float(pt["lat"])
            lon = float(pt["lon"])
        elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
            lat = float(pt[0])
            lon = float(pt[1])
        else:
            raise ValueError(f"Invalid point structure: {pt}")
        ring.append([round(lon, 6), round(lat, 6)])

    # Automatically close the polygon ring if not already closed
    if ring[0] != ring[-1]:
        ring.append(list(ring[0]))

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
            }
        ],
    }


def parse_polygon_aoi(raw_value: str) -> dict[str, Any]:
    """Parse and validate a GeoJSON FeatureCollection entered by the user."""
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("AOI must be valid JSON.") from exc

    if not isinstance(parsed, Mapping):
        raise ValueError("AOI must be a GeoJSON FeatureCollection object.")

    try:
        return PolygonAoi.model_validate(parsed).model_dump(mode="json")
    except ValidationError as exc:
        first_error = exc.errors()[0].get("msg", "invalid GeoJSON structure")
        raise ValueError(f"AOI is invalid: {first_error}") from exc


def extract_map_points(map_data: Any) -> list[dict[str, float | None]]:
    """
    Best-effort extraction of ``[{lon, lat, value}]`` points from an
    unrecognized ``map_data`` shape.

    FortyGuard has not documented ``map_data``'s structure, so this looks
    under a few plausible container keys and coordinate key spellings and
    silently skips anything that doesn't look like a point. Callers should
    treat an empty result as "nothing recognizable", not "no data exists".
    """
    candidates: Any = map_data
    if isinstance(candidates, Mapping):
        for key in ("points", "features", "data"):
            value = candidates.get(key)
            if isinstance(value, list):
                candidates = value
                break

    if not isinstance(candidates, list):
        return []

    points: list[dict[str, float | None]] = []
    for item in candidates:
        if not isinstance(item, Mapping):
            continue

        lon = _first_numeric(item, ("lon", "lng", "longitude"))
        lat = _first_numeric(item, ("lat", "latitude"))
        if lon is None or lat is None:
            continue

        value = _first_numeric(item, ("value",))
        points.append({"lon": lon, "lat": lat, "value": value})

    return points


def _first_numeric(item: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def is_polygon_feature_collection(map_data: Any) -> bool:
    """
    Check whether ``map_data`` is itself a GeoJSON FeatureCollection of
    Polygon/MultiPolygon features.

    Confirmed by a real Phase 4 FortyGuard capture: a completed Heatmap's
    ``map_data`` is a FeatureCollection of Polygon "tiles", not a flat list
    of points. This check lets the map renderer prefer that real shape while
    still falling back to point-extraction for any other shape.
    """
    if not isinstance(map_data, Mapping) or map_data.get("type") != "FeatureCollection":
        return False
    features = map_data.get("features")
    if not isinstance(features, list) or not features:
        return False
    return all(
        isinstance(feature, Mapping)
        and isinstance(feature.get("geometry"), Mapping)
        and feature["geometry"].get("type") in ("Polygon", "MultiPolygon")
        for feature in features
    )


from frontend.utils.colors import (
    FALLBACK_RGBA,
    compute_temperature_bounds,
    temperature_to_rgba,
)


def _format_temp_prop(val: Any) -> str:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return f"{float(val):.2f} °C"
    return "N/A"


def build_temperature_colored_geojson(
    feature_collection: Mapping[str, Any],
    property_key: str = "average_temperature",
) -> dict[str, Any]:
    """
    Return a copy of a Polygon FeatureCollection with a ``fill_color``
    property added to each feature, scaled from ``property_key`` when it's
    present and numeric. Features without a usable value get a neutral
    default color instead of being dropped. Also formats string properties
    for clean tooltip rendering. Does not mutate the input.
    """
    features = feature_collection.get("features", [])
    if not isinstance(features, list):
        return {"type": "FeatureCollection", "features": []}

    bounds = compute_temperature_bounds(features, property_key=property_key)
    min_val, max_val = bounds if bounds is not None else (0.0, 0.0)

    colored_features = []
    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        properties = dict(feature.get("properties") or {})
        value = properties.get(property_key)

        if bounds is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
            properties["fill_color"] = temperature_to_rgba(float(value), min_val, max_val)
        else:
            properties["fill_color"] = list(FALLBACK_RGBA)

        # Add formatted strings for clean tooltip presentation
        avg_temp = properties.get("average_temperature", value)
        properties["average_temperature_str"] = _format_temp_prop(avg_temp)
        properties["min_temperature_str"] = _format_temp_prop(properties.get("min_temperature"))
        properties["max_temperature_str"] = _format_temp_prop(properties.get("max_temperature"))
        tile_id = properties.get("tile_id")
        properties["tile_id_str"] = str(tile_id) if tile_id is not None else "N/A"

        colored_features.append({**feature, "properties": properties})

    return {"type": feature_collection.get("type", "FeatureCollection"), "features": colored_features}


def compute_aoi_centroid(polygon_aoi: Mapping[str, Any]) -> tuple[float, float] | None:
    """
    Compute a simple ``(lat, lon)`` centroid of the first polygon ring in an
    AOI FeatureCollection, for use as a map's initial view state.

    Returns ``None`` when no usable ring is found.
    """
    features = polygon_aoi.get("features")
    if not isinstance(features, list):
        return None

    for feature in features:
        if not isinstance(feature, Mapping):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping):
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            continue
        ring = coordinates[0]
        if not isinstance(ring, list) or not ring:
            continue
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]  # drop the duplicated closing vertex

        lons = [pos[0] for pos in ring if isinstance(pos, list) and len(pos) == 2]
        lats = [pos[1] for pos in ring if isinstance(pos, list) and len(pos) == 2]
        if not lons or not lats:
            continue

        return sum(lats) / len(lats), sum(lons) / len(lons)

    return None


def build_heatmap_request_payload(
    polygon_aoi: Mapping[str, Any],
    selected_date: date,
    selected_time: time,
    granularity: int,
) -> dict[str, Any]:
    """Build the exact documented request body after local validation."""
    validated_aoi = PolygonAoi.model_validate(polygon_aoi)
    date_time = DateTimeFilter(
        start_date=selected_date.isoformat(),
        start_time=selected_time.strftime("%H:%M"),
        filter_type=1,
    )
    request = HeatmapRequest(
        polygon_aoi=validated_aoi,
        date_time=date_time,
        granularity=granularity,
    )
    return request.model_dump(mode="json")
