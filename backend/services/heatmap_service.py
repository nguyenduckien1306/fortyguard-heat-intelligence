"""Heatmap business logic layer."""

from __future__ import annotations

from backend.api.client import FortyGuardClient
from backend.api.exceptions import AuthenticationError, FortyGuardClientError
from backend.config import Settings, get_settings
from backend.models.common import ActivityStatusResponse
from backend.models.heatmap import HeatmapRequest, HeatmapSubmissionResponse


class HeatmapService:
    """Service layer between API routes and the FortyGuard client."""

    def __init__(
        self,
        client: FortyGuardClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or FortyGuardClient(settings=self._settings)

    @property
    def client(self) -> FortyGuardClient:
        return self._client

    def _ensure_api_key_configured(self) -> None:
        if not self._settings.fortyguard_api_configured:
            raise AuthenticationError("FortyGuard API key is not configured.")

    def submit_heatmap(self, request: HeatmapRequest) -> HeatmapSubmissionResponse:
        """Submit a heatmap analysis request via the FortyGuard client."""
        self._ensure_api_key_configured()
        return self._client.create_heatmap_request(request)

    def get_heatmap_status(self, activity_id: str) -> ActivityStatusResponse:
        """Retrieve heatmap task status for an activity."""
        self._ensure_api_key_configured()
        return self._client.get_activity_status(activity_id)

    def poll_heatmap(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> ActivityStatusResponse:
        """Poll heatmap activity until completion, failure, or timeout."""
        self._ensure_api_key_configured()
        return self._client.poll_heatmap_result(
            activity_id,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )
