"""Heat Intelligence business logic layer."""

from __future__ import annotations

from backend.api.client import FortyGuardClient
from backend.api.exceptions import AuthenticationError
from backend.config import Settings, get_settings
from backend.models.common import ActivityStatusResponse
from backend.models.heat_intelligence import (
    HeatIntelligenceRequest,
    HeatIntelligenceSubmissionResponse,
)


class HeatIntelligenceService:
    """Service layer between API routes and the FortyGuard client for Heat Intelligence."""

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

    def submit_heat_intelligence(
        self, request: HeatIntelligenceRequest
    ) -> HeatIntelligenceSubmissionResponse:
        """Submit a Heat Intelligence analysis request via the FortyGuard client."""
        self._ensure_api_key_configured()
        return self._client.create_heat_intelligence_request(request)

    def get_heat_intelligence_status(self, activity_id: str) -> ActivityStatusResponse:
        """Retrieve Heat Intelligence task status for an activity."""
        self._ensure_api_key_configured()
        return self._client.get_activity_status(activity_id)

    def poll_heat_intelligence(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> ActivityStatusResponse:
        """Poll Heat Intelligence activity until completion, failure, or timeout."""
        self._ensure_api_key_configured()
        return self._client.poll_heat_intelligence_result(
            activity_id,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )

    def fetch_report(self, activity_id: str) -> bytes:
        """Fetch the completed Heat Intelligence report PDF bytes by activity ID.

        Validates API key, retrieves task status, and downloads the PDF
        from the signed URL — all server-side so no signed URLs leak to the frontend.
        """
        self._ensure_api_key_configured()
        return self._client.get_heat_intelligence_report_pdf(activity_id)
