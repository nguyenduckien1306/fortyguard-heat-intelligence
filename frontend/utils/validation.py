"""Centralized pure validation core for FortyGuard Heat Intelligence.

Provides deterministic, pure validation functions for both Heat Intelligence
and Heatmap workflows. Validation functions are pure and perform ZERO network I/O.

SUBMISSION BOUNDARY INVARIANT:
    Every backend/API network invocation must occur strictly after a successful
    centralized ValidationResult. If validation fails, no network requests,
    credits, activity IDs, or history records are generated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type, datetime, time as time_type
import json
import math
import re
from typing import Any, Mapping, Sequence

# Confirmed valid analysis category options from FortyGuard documentation
VALID_ANALYSIS_CATEGORIES: frozenset[str] = frozenset({
    "geographic",
    "environmental",
    "urban",
    "events",
    "anthropogenic",
})

# Terrestrial temperature validation bounds (application sanity check)
MIN_VALID_TEMPERATURE = -100.0
MAX_VALID_TEMPERATURE = 100.0

# Geographic coordinate bounds
MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


@dataclass
class ValidationResult:
    """Represents the outcome of a pre-flight request validation.

    Attributes:
        is_valid: True if there are zero blocking errors.
        field_errors: Dict mapping field names (e.g. 'latitude') to concise user error messages.
        errors: Complete ordered list of all blocking error messages.
        warnings: Non-blocking notices or recommendations.
    """

    is_valid: bool = True
    field_errors: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_field_error(self, field_name: str, message: str) -> None:
        """Add a field-level error and mark validation as failed."""
        self.is_valid = False
        self.field_errors[field_name] = message
        if message not in self.errors:
            self.errors.append(message)

    def add_error(self, message: str) -> None:
        """Add a general error and mark validation as failed."""
        self.is_valid = False
        if message not in self.errors:
            self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a non-blocking warning note."""
        if message not in self.warnings:
            self.warnings.append(message)


# ──────────────────────────────────────────────────────────────────────────────
# Field Validators (Pure)
# ──────────────────────────────────────────────────────────────────────────────


def validate_latitude(value: Any) -> tuple[bool, str | None]:
    """Validate latitude coordinate.

    Must be a finite number between -90.0 and 90.0.
    Booleans are explicitly rejected.
    """
    if value is None:
        return False, "Latitude is required."

    if isinstance(value, bool):
        return False, "Latitude must be a valid number between -90° and 90°."

    try:
        val = float(value)
    except (ValueError, TypeError):
        return False, "Latitude must be a valid number between -90° and 90°."

    if math.isnan(val) or math.isinf(val):
        return False, "Latitude must be a finite number."

    if val < MIN_LATITUDE or val > MAX_LATITUDE:
        return False, f"Invalid latitude ({val}). Latitude must be between -90° and 90°."

    return True, None


def validate_longitude(value: Any) -> tuple[bool, str | None]:
    """Validate longitude coordinate.

    Must be a finite number between -180.0 and 180.0.
    Booleans are explicitly rejected.
    """
    if value is None:
        return False, "Longitude is required."

    if isinstance(value, bool):
        return False, "Longitude must be a valid number between -180° and 180°."

    try:
        val = float(value)
    except (ValueError, TypeError):
        return False, "Longitude must be a valid number between -180° and 180°."

    if math.isnan(val) or math.isinf(val):
        return False, "Longitude must be a finite number."

    if val < MIN_LONGITUDE or val > MAX_LONGITUDE:
        return False, f"Invalid longitude ({val}). Longitude must be between -180° and 180°."

    return True, None


def validate_temperature(value: Any) -> tuple[bool, str | None]:
    """Validate observed temperature in degrees Celsius.

    Must be a finite number within the application terrestrial sanity range (-100°C to 100°C).
    Booleans are explicitly rejected.
    """
    if value is None:
        return False, "Observed temperature is required."

    if isinstance(value, bool):
        return False, "Observed temperature must be a valid number between -100°C and 100°C."

    try:
        val = float(value)
    except (ValueError, TypeError):
        return False, "Observed temperature must be a valid number between -100°C and 100°C."

    if math.isnan(val) or math.isinf(val):
        return False, "Observed temperature must be a finite number."

    if val < MIN_VALID_TEMPERATURE or val > MAX_VALID_TEMPERATURE:
        return (
            False,
            f"Observed temperature ({val}°C) must be between -100°C and 100°C.",
        )

    return True, None


def validate_analysis_categories(categories: Any) -> tuple[bool, str | None]:
    """Validate selected Heat Intelligence analysis categories.

    Must be a non-empty sequence containing only confirmed FortyGuard dimensions.
    """
    if not categories or not isinstance(categories, (list, tuple, set, frozenset)):
        return False, "Select at least one analysis category."

    cat_list = [str(c).strip().lower() for c in categories if c]
    if not cat_list:
        return False, "Select at least one analysis category."

    invalid = [c for c in cat_list if c not in VALID_ANALYSIS_CATEGORIES]
    if invalid:
        allowed = ", ".join(sorted(VALID_ANALYSIS_CATEGORIES))
        return (
            False,
            f"Unrecognized analysis category: {', '.join(invalid)}. Allowed: {allowed}.",
        )

    return True, None


def validate_date(value: Any) -> tuple[bool, str | None]:
    """Validate analysis date (YYYY-MM-DD)."""
    if value is None:
        return False, "Analysis date is required."

    if isinstance(value, date_type):
        return True, None

    if isinstance(value, str):
        val_str = value.strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val_str):
            return False, "Date must use YYYY-MM-DD format."
        try:
            parsed = datetime.strptime(val_str, "%Y-%m-%d").date()
            if parsed.strftime("%Y-%m-%d") != val_str:
                return False, "Date must be a valid calendar date in YYYY-MM-DD format."
            return True, None
        except ValueError:
            return False, "Date must be a valid calendar date in YYYY-MM-DD format."

    return False, "Invalid date format. Expected YYYY-MM-DD."


def validate_time(value: Any) -> tuple[bool, str | None]:
    """Validate analysis time (HH:MM)."""
    if value is None:
        return False, "Analysis time is required."

    if isinstance(value, time_type):
        return True, None

    if isinstance(value, str):
        val_str = value.strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", val_str):
            return False, "Time must use HH:MM format (24-hour clock)."
        return True, None

    return False, "Invalid time format. Expected HH:MM."


def validate_granularity(value: Any) -> tuple[bool, str | None]:
    """Validate heatmap spatial granularity (integer >= 1)."""
    if value is None:
        return False, "Granularity is required."

    if isinstance(value, bool):
        return False, "Granularity must be a positive whole number (e.g. 100)."

    try:
        val = int(value)
    except (ValueError, TypeError):
        return False, "Granularity must be a positive whole number (e.g. 100)."

    if val < 1:
        return False, f"Granularity ({val}) must be at least 1 meter."

    return True, None


# ──────────────────────────────────────────────────────────────────────────────
# GeoJSON AOI Structural Validation (Pure)
# ──────────────────────────────────────────────────────────────────────────────


def validate_geojson_polygon_aoi(
    raw_data: Any,
) -> ValidationResult:
    """Validate that the provided AOI is a valid GeoJSON FeatureCollection with 2D Polygons.

    Contract:
    - Must be a valid JSON object / dict.
    - type == 'FeatureCollection'.
    - features list must not be empty.
    - Each feature must be a Feature with geometry.type == 'Polygon'.
    - Each ring must contain at least 4 positions.
    - Each ring must be closed (first coordinate == last coordinate).
    - Each position must be exactly [longitude, latitude] (2D).
    - Coordinates must satisfy -180 <= longitude <= 180 and -90 <= latitude <= 90.
    """
    res = ValidationResult()

    if raw_data is None:
        res.add_field_error("polygon_aoi", "Area of Interest (GeoJSON) is required.")
        return res

    data: Any = raw_data
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            res.add_field_error("polygon_aoi", f"AOI is not valid JSON: {exc.msg} (line {exc.lineno}).")
            return res

    if not isinstance(data, Mapping):
        res.add_field_error("polygon_aoi", "AOI must be a GeoJSON FeatureCollection object.")
        return res

    if data.get("type") != "FeatureCollection":
        res.add_field_error(
            "polygon_aoi",
            f"Expected GeoJSON 'FeatureCollection', got '{data.get('type', 'Unknown')}'.",
        )
        return res

    features = data.get("features")
    if not isinstance(features, list) or len(features) == 0:
        res.add_field_error("polygon_aoi", "FeatureCollection must contain at least one feature.")
        return res

    for f_idx, feature in enumerate(features):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            res.add_field_error(
                "polygon_aoi",
                f"Feature at index {f_idx} must be a GeoJSON Feature object.",
            )
            return res

        geom = feature.get("geometry")
        if not isinstance(geom, Mapping):
            res.add_field_error(
                "polygon_aoi",
                f"Feature at index {f_idx} is missing a valid geometry object.",
            )
            return res

        geom_type = geom.get("type")
        if geom_type != "Polygon":
            res.add_field_error(
                "polygon_aoi",
                f"Feature at index {f_idx} has unsupported geometry '{geom_type}'. Only 'Polygon' is supported.",
            )
            return res

        coordinates = geom.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) == 0:
            res.add_field_error(
                "polygon_aoi",
                f"Polygon at feature {f_idx} has empty coordinates.",
            )
            return res

        for r_idx, ring in enumerate(coordinates):
            if not isinstance(ring, list) or len(ring) < 4:
                res.add_field_error(
                    "polygon_aoi",
                    f"Polygon ring {r_idx} in feature {f_idx} must have at least 4 coordinate positions.",
                )
                return res

            # Check closure
            if ring[0] != ring[-1]:
                res.add_field_error(
                    "polygon_aoi",
                    f"Polygon ring {r_idx} in feature {f_idx} is not closed (first position {ring[0]} does not match last {ring[-1]}).",
                )
                return res

            # Check position dimensionality and coordinate bounds
            for p_idx, pos in enumerate(ring):
                if not isinstance(pos, (list, tuple)) or len(pos) != 2:
                    res.add_field_error(
                        "polygon_aoi",
                        f"Position {p_idx} in ring {r_idx} must be exactly 2D [longitude, latitude].",
                    )
                    return res

                lon_val, lat_val = pos
                is_lon_ok, lon_err = validate_longitude(lon_val)
                if not is_lon_ok:
                    res.add_field_error(
                        "polygon_aoi",
                        f"Invalid longitude at feature {f_idx}, ring {r_idx}, position {p_idx}: {lon_err}",
                    )
                    return res

                is_lat_ok, lat_err = validate_latitude(lat_val)
                if not is_lat_ok:
                    res.add_field_error(
                        "polygon_aoi",
                        f"Invalid latitude at feature {f_idx}, ring {r_idx}, position {p_idx}: {lat_err}",
                    )
                    return res

    return res


# ──────────────────────────────────────────────────────────────────────────────
# Aggregated Request Validators (Pure)
# ──────────────────────────────────────────────────────────────────────────────


def validate_heat_intelligence_request(
    latitude: Any,
    longitude: Any,
    temperature: Any,
    date_val: Any,
    categories: Any,
) -> ValidationResult:
    """Validate complete Heat Intelligence request parameters before submission.

    Aggregates all field validators and returns a unified ValidationResult.
    """
    res = ValidationResult()

    is_lat_ok, lat_err = validate_latitude(latitude)
    if not is_lat_ok and lat_err:
        res.add_field_error("latitude", lat_err)

    is_lon_ok, lon_err = validate_longitude(longitude)
    if not is_lon_ok and lon_err:
        res.add_field_error("longitude", lon_err)

    is_temp_ok, temp_err = validate_temperature(temperature)
    if not is_temp_ok and temp_err:
        res.add_field_error("temperature", temp_err)

    is_date_ok, date_err = validate_date(date_val)
    if not is_date_ok and date_err:
        res.add_field_error("date", date_err)

    is_cat_ok, cat_err = validate_analysis_categories(categories)
    if not is_cat_ok and cat_err:
        res.add_field_error("analysis", cat_err)

    # Optional non-blocking warnings
    if is_temp_ok and isinstance(temperature, (int, float)) and not isinstance(temperature, bool):
        if temperature > 55.0:
            res.add_warning("Observed temperature is exceptionally high (>55°C).")
        elif temperature < -40.0:
            res.add_warning("Observed temperature is exceptionally low (<-40°C).")

    return res


def validate_heatmap_request(
    polygon_aoi: Any,
    date_val: Any,
    time_val: Any,
    granularity: Any,
    location_label: str = "",
) -> ValidationResult:
    """Validate complete Heatmap request parameters before submission.

    Note: location_label is optional.
    """
    res = validate_geojson_polygon_aoi(polygon_aoi)

    is_date_ok, date_err = validate_date(date_val)
    if not is_date_ok and date_err:
        res.add_field_error("date", date_err)

    is_time_ok, time_err = validate_time(time_val)
    if not is_time_ok and time_err:
        res.add_field_error("time", time_err)

    is_gran_ok, gran_err = validate_granularity(granularity)
    if not is_gran_ok and gran_err:
        res.add_field_error("granularity", gran_err)

    return res
