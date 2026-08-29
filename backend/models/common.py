"""Shared Pydantic models for FortyGuard task management responses."""

from typing import Any

from pydantic import BaseModel, Field


class FortyGuardEnvelope(BaseModel):
    """Documented FortyGuard API response envelope."""

    error: bool
    status_code: int
    message: str
    data: dict[str, Any] | None = None


class ActivityStatusResponse(BaseModel):
    """Normalized response from GET /v1/status/{activity_id}."""

    activity_id: str
    status: str = Field(
        ...,
        description="Task status: Processing, Completed, or Failed.",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Endpoint-specific result when the task has completed successfully.",
    )
    diagnostic: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized diagnostic information for failed or non-terminal tasks.",
    )


class CreditsUsageResponse(BaseModel):
    """Response from the API credits usage endpoint."""

    credits_used: float | None = None
    credits_remaining: float | None = None
