"""Pydantic models for the documented heatmap request and response structures."""

from datetime import date as date_type
from math import isfinite
from re import fullmatch
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator


class Geometry(BaseModel):
    """GeoJSON geometry for a polygon area of interest."""

    type: Literal["Polygon"]
    coordinates: list[list[list[float]]] = Field(..., min_length=1)

    @field_validator("coordinates")
    @classmethod
    def validate_polygon_coordinates(
        cls, coordinates: list[list[list[float]]]
    ) -> list[list[list[float]]]:
        """Validate the structural parts of a GeoJSON Polygon."""
        for ring in coordinates:
            if len(ring) < 4:
                raise ValueError("Polygon rings must contain at least four positions.")
            if ring[0] != ring[-1]:
                raise ValueError("Polygon rings must be closed.")
            for position in ring:
                if len(position) != 2:
                    raise ValueError(
                        "Polygon positions must be [longitude, latitude]."
                    )
                if not all(isfinite(value) for value in position):
                    raise ValueError("Polygon coordinates must be finite numbers.")
                lon, lat = position
                if lon < -180.0 or lon > 180.0:
                    raise ValueError(f"Longitude ({lon}) must be between -180 and 180.")
                if lat < -90.0 or lat > 90.0:
                    raise ValueError(f"Latitude ({lat}) must be between -90 and 90.")
        return coordinates


class Feature(BaseModel):
    """GeoJSON feature within a FeatureCollection."""

    type: Literal["Feature"]
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: Geometry


class FeatureCollection(BaseModel):
    """GeoJSON FeatureCollection wrapper."""

    type: Literal["FeatureCollection"]
    features: list[Feature] = Field(..., min_length=1)


class PolygonAoi(BaseModel):
    """Area of interest expressed as a GeoJSON FeatureCollection."""

    type: Literal["FeatureCollection"]
    features: list[Feature] = Field(..., min_length=1)


class DateTimeFilter(BaseModel):
    """Date and time filter for heatmap analysis."""

    start_date: str = Field(..., description="Start date in YYYY-MM-DD format.")
    start_time: str = Field(..., description="Start time in HH:MM format.")
    filter_type: StrictInt

    @field_validator("start_date")
    @classmethod
    def validate_start_date(cls, value: str) -> str:
        if not fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("start_date must use YYYY-MM-DD format.")
        try:
            parsed = date_type.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("start_date must be a valid calendar date.") from exc
        if parsed.isoformat() != value:
            raise ValueError("start_date must use YYYY-MM-DD format.")
        return value

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: str) -> str:
        if not fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("start_time must use HH:MM format.")
        return value


class HeatmapRequest(BaseModel):
    """Documented POST /v1/heatmap request body."""

    polygon_aoi: PolygonAoi
    date_time: DateTimeFilter
    granularity: StrictInt


class HeatmapSubmissionResponse(BaseModel):
    """Normalized response after submitting a heatmap analysis job."""

    activity_id: str


class HeatmapSubmitAPIResponse(BaseModel):
    """FastAPI response returned after heatmap submission."""

    activity_id: str
    message: str = "Heatmap submitted successfully"
