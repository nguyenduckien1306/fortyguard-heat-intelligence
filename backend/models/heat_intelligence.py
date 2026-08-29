"""Pydantic models for the confirmed FortyGuard Heat Intelligence request and response structures."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


VALID_ANALYSIS_OPTIONS = frozenset({
    "geographic",
    "environmental",
    "urban",
    "events",
    "anthropogenic",
})


class HeatIntelligenceRequest(BaseModel):
    """Confirmed POST /v1/heat_intelligence request body."""

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate")
    temperature: float = Field(..., description="Temperature value in degrees Celsius")
    date: str = Field(..., description="Date for the reading in YYYY-MM-DD format")
    analysis: list[str] = Field(
        default=["environmental"],
        min_length=1,
        description="Analysis options: geographic, environmental, urban, events, anthropogenic",
    )

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("date must be in YYYY-MM-DD format") from exc
        return value

    @field_validator("analysis")
    @classmethod
    def validate_analysis_options(cls, values: list[str]) -> list[str]:
        invalid = [v for v in values if v not in VALID_ANALYSIS_OPTIONS]
        if invalid:
            raise ValueError(
                f"Invalid analysis options: {invalid}. Must be subset of: {sorted(VALID_ANALYSIS_OPTIONS)}"
            )
        return values


class HeatIntelligenceSubmissionResponse(BaseModel):
    """Normalized response after submitting a Heat Intelligence analysis job."""

    activity_id: str


class HeatIntelligenceSubmitAPIResponse(BaseModel):
    """FastAPI response returned after Heat Intelligence submission."""

    activity_id: str
    message: str = "Heat intelligence task submitted successfully"
