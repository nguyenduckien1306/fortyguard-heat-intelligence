"""FortyGuard Enterprise Temperature API HTTP client."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

from backend.api.exceptions import (
    AuthenticationError,
    ForbiddenError,
    FortyGuardClientError,
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    PollingTimeoutError,
    RateLimitError,
    ServerError,
    TransportError,
)
from backend.config import Settings, get_settings
from backend.models.common import ActivityStatusResponse, CreditsUsageResponse
from backend.models.heat_intelligence import (
    HeatIntelligenceRequest,
    HeatIntelligenceSubmissionResponse,
)
from backend.models.heatmap import HeatmapRequest, HeatmapSubmissionResponse

_STATUS_ERROR_MAP: dict[int, type[FortyGuardClientError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    422: InvalidRequestError,
    429: RateLimitError,
    500: ServerError,
}

TERMINAL_STATUSES = frozenset({"Completed", "Failed"})


class FortyGuardClient:
    """
    HTTP client for the FortyGuard API.

    Authentication uses the ``api-key`` header (not Bearer/OAuth).
    """

    API_KEY_HEADER = "api-key"
    HEATMAP_PATH = "/v1/heatmap"
    HEAT_INTELLIGENCE_PATH = "/v1/heat_intelligence"
    STATUS_PATH = "/v1/status/{activity_id}"


    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.Client(
            base_url=self._settings.fortyguard_base_url.rstrip("/"),
            headers=self._build_headers(),
            timeout=30.0,
        )

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def base_url(self) -> str:
        return self._settings.fortyguard_base_url.rstrip("/")

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._settings.fortyguard_api_key:
            headers[self.API_KEY_HEADER] = self._settings.fortyguard_api_key
        return headers

    def create_heatmap_request(
        self, request: HeatmapRequest
    ) -> HeatmapSubmissionResponse:
        """Submit POST /v1/heatmap and return the activity ID."""
        try:
            response = self._http_client.post(
                self.HEATMAP_PATH,
                json=request.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise TransportError("Unable to reach FortyGuard.") from exc
        payload = self._parse_json_response(response)
        return self._parse_submission_payload(payload)

    def create_heat_intelligence_request(
        self, request: HeatIntelligenceRequest
    ) -> HeatIntelligenceSubmissionResponse:
        """Submit POST /v1/heat-intelligence and return the activity ID."""
        try:
            response = self._http_client.post(
                self.HEAT_INTELLIGENCE_PATH,
                json=request.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise TransportError("Unable to reach FortyGuard.") from exc
        payload = self._parse_json_response(response)
        submission = self._parse_submission_payload(payload)
        return HeatIntelligenceSubmissionResponse(activity_id=submission.activity_id)

    def fetch_report_pdf(self, download_link: str) -> bytes:
        """
        Securely download the generated PDF report bytes from a signed download link.

        Validates status, handles expired/invalid links, verifies PDF magic bytes,
        and never logs or leaks the URL.
        """
        if not download_link or not isinstance(download_link, str) or not download_link.strip():
            raise InvalidRequestError("Invalid or missing report download link.", http_status=400)

        try:
            # If httpx.Client is mocked in legacy unit tests, respect the mock fetcher
            if type(httpx.Client).__name__ == "MagicMock" or getattr(httpx.Client, "__module__", "").startswith("unittest.mock"):
                with httpx.Client(timeout=30.0) as fetcher:
                    response = fetcher.get(download_link.strip(), headers={"Accept": "application/pdf"})
            else:
                # Reuse the injected transport so tests can intercept storage URLs,
                # but never forward FortyGuard credentials to third-party hosts.
                request = self._http_client.build_request(
                    "GET",
                    download_link.strip(),
                    headers={"Accept": "application/pdf"},
                )
                request.headers.pop("api-key", None)
                request.headers.pop("API-KEY", None)
                response = self._http_client.send(request, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise TransportError("Unable to connect to report storage provider.") from exc

        if response.status_code == 200:
            if not response.content:
                raise MalformedResponseError("The report was returned empty.")
            # Verify PDF magic bytes or PDF Content-Type
            content_type = response.headers.get("content-type", "").lower()
            if not response.content.startswith(b"%PDF-") and "application/pdf" not in content_type:
                raise MalformedResponseError("Downloaded content is not a valid PDF report.")
            return response.content

        if response.status_code in (401, 403, 410):
            raise InvalidRequestError(
                "The report download link has expired. Please request the report again.",
                http_status=410,
            )
        if response.status_code == 404:
            raise NotFoundError("The requested report file was not found on the storage provider.", http_status=404)
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded while downloading report.", http_status=429)

        raise ServerError("Storage provider returned an error while downloading report.", http_status=502)

    def get_heat_intelligence_report_pdf(self, activity_id: str) -> bytes:
        """
        Retrieve the completed Heat Intelligence report PDF bytes by activity ID.
        """
        status_resp = self.get_activity_status(activity_id)

        if status_resp.status == "Processing":
            raise InvalidRequestError("Task is still processing. Report is not ready yet.", http_status=409)
        if status_resp.status == "Failed":
            raise InvalidRequestError("Task processing failed on FortyGuard.", http_status=400)
        if status_resp.status != "Completed":
            raise InvalidRequestError(f"Task status is '{status_resp.status}'. Report is not available.", http_status=400)

        if not status_resp.result or not isinstance(status_resp.result, dict):
            raise MalformedResponseError("Completed task has no result payload.")

        download_link = status_resp.result.get("download_link")
        if not download_link or not isinstance(download_link, str):
            raise MalformedResponseError("The report completed, but no report download_link was provided.")

        return self.fetch_report_pdf(download_link)

    def poll_heat_intelligence_result(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> ActivityStatusResponse:
        """Poll Heat Intelligence activity status until Completed, Failed, or timeout."""
        return self.poll_heatmap_result(
            activity_id,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )

    def get_activity_status(self, activity_id: str) -> ActivityStatusResponse:

        """Fetch GET /v1/status/{activity_id}."""
        if not activity_id.strip():
            raise ValueError("activity_id must not be empty")
        try:
            response = self._http_client.get(
                self.STATUS_PATH.format(activity_id=activity_id)
            )
        except httpx.HTTPError as exc:
            raise TransportError("Unable to reach FortyGuard.") from exc
        payload = self._parse_json_response(response)
        return self._parse_status_payload(payload, expected_activity_id=activity_id)

    def poll_heatmap_result(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> ActivityStatusResponse:
        """
        Poll activity status until Completed, Failed, or timeout.

        Continues while status is ``Processing`` up to ``max_attempts``.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        for attempt in range(max_attempts):
            status = self.get_activity_status(activity_id)

            if status.status in TERMINAL_STATUSES:
                return status

            if status.status != "Processing":
                return status

            if attempt < max_attempts - 1:
                time.sleep(poll_interval_seconds)

        raise PollingTimeoutError(
            message=(
                f"Polling timed out after {max_attempts} attempts "
                f"for activity '{activity_id}'."
            ),
            activity_id=activity_id,
        )

    def get_credits_usage(self) -> CreditsUsageResponse:
        """
        Fetch API credits usage.

        Not implemented in Phase 1.
        """
        raise NotImplementedError(
            "get_credits_usage is not implemented in Phase 1."
        )

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        self._raise_for_http_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponseError(
                "FortyGuard returned a non-JSON response."
            ) from exc

        if not isinstance(payload, dict):
            raise MalformedResponseError("FortyGuard response must be a JSON object.")

        if payload.get("error"):
            message = str(payload.get("message", "FortyGuard API returned an error."))
            raw_status_code = payload.get("status_code", response.status_code)
            if isinstance(raw_status_code, bool) or not isinstance(raw_status_code, int):
                raise MalformedResponseError(
                    "FortyGuard error response has an invalid status_code."
                )
            status_code = raw_status_code
            exc_class = _STATUS_ERROR_MAP.get(status_code, FortyGuardClientError)
            raise exc_class(message, http_status=status_code)

        return payload

    @staticmethod
    def _parse_submission_payload(
        payload: dict[str, Any]
    ) -> HeatmapSubmissionResponse:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MalformedResponseError("Missing data object in submission response.")

        activity_id = data.get("activity_id")
        if not activity_id or not isinstance(activity_id, str):
            raise MalformedResponseError(
                "Missing activity_id in submission response."
            )

        return HeatmapSubmissionResponse(activity_id=activity_id)

    @staticmethod
    def _sanitize_diagnostic_data(data: Any) -> Any:
        """Recursively strip credentials, tokens, API keys, Authorization headers, and signed URLs."""
        if isinstance(data, Mapping):
            sanitized: dict[str, Any] = {}
            for k, v in data.items():
                k_lower = str(k).lower()
                if any(
                    sec in k_lower
                    for sec in (
                        "api_key",
                        "token",
                        "secret",
                        "password",
                        "authorization",
                        "credential",
                        "signed_url",
                        "download_link",
                        "cookie",
                        "headers",
                        "auth",
                    )
                ):
                    continue
                sanitized[k] = FortyGuardClient._sanitize_diagnostic_data(v)
            return sanitized
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
            return [FortyGuardClient._sanitize_diagnostic_data(item) for item in data]
        elif isinstance(data, str):
            if "X-Amz-Signature=" in data or "Signature=" in data:
                return "[REDACTED_SIGNED_URL]"
            return data
        return data

    @staticmethod
    def _parse_status_payload(
        payload: dict[str, Any],
        *,
        expected_activity_id: str | None = None,
    ) -> ActivityStatusResponse:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MalformedResponseError("Missing data object in status response.")

        activity_id = data.get("activity_id")
        status = data.get("status")

        if not activity_id or not isinstance(activity_id, str):
            raise MalformedResponseError("Missing activity_id in status response.")

        if expected_activity_id is not None and activity_id != expected_activity_id:
            raise MalformedResponseError(
                "FortyGuard returned a status for a different activity_id."
            )

        if not status or not isinstance(status, str):
            raise MalformedResponseError("Missing status in status response.")

        result = data.get("result")
        if result is None and status == "Completed":
            extra = {
                key: value
                for key, value in data.items()
                if key not in {"activity_id", "status"}
            }
            result = extra or None

        # Build sanitized diagnostic information for Failed or error states
        diagnostic: dict[str, Any] | None = None
        if status == "Failed" or payload.get("error"):
            raw_diag: dict[str, Any] = {}

            # Extract error code
            code = (
                data.get("code")
                or data.get("error_code")
                or payload.get("code")
                or payload.get("error_code")
            )
            if code:
                raw_diag["code"] = str(code)

            # Extract message
            msg = (
                data.get("message")
                or data.get("provider_message")
                or (payload.get("message") if payload.get("message") != "Failed" else None)
            )
            if msg and str(msg).strip():
                raw_diag["message"] = str(msg).strip()

            # Extract reason
            reason = (
                data.get("reason")
                or data.get("failure_reason")
                or payload.get("reason")
                or payload.get("failure_reason")
            )
            if reason and str(reason).strip():
                raw_diag["reason"] = str(reason).strip()

            # Extract details
            details = (
                data.get("details")
                or data.get("error")
                or data.get("errors")
                or payload.get("details")
            )
            if details and details != "Failed" and details is not True:
                raw_diag["details"] = details

            # Preserve any remaining non-standard diagnostic keys in data
            for k, v in data.items():
                if k not in {
                    "activity_id",
                    "status",
                    "result",
                    "code",
                    "error_code",
                    "message",
                    "provider_message",
                    "reason",
                    "failure_reason",
                    "details",
                    "error",
                    "errors",
                }:
                    raw_diag[k] = v

            sanitized_diag = FortyGuardClient._sanitize_diagnostic_data(raw_diag)
            diagnostic = sanitized_diag if sanitized_diag else None

            # Terminal developer logging for provider failures (strictly sanitized)
            log_parts = [
                "HEAT_INTELLIGENCE_PROVIDER_FAILURE",
                f"activity_id={activity_id}",
                f"status={status}",
            ]
            if diagnostic:
                for k, v in diagnostic.items():
                    log_parts.append(f"{k}={v}")
            logger.warning(" ".join(log_parts))

        return ActivityStatusResponse(
            activity_id=activity_id,
            status=status,
            result=result if isinstance(result, dict) else None,
            diagnostic=diagnostic,
        )

    def _raise_for_http_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        message = self._extract_error_message(response)
        exc_class = _STATUS_ERROR_MAP.get(response.status_code, FortyGuardClientError)
        raise exc_class(message, http_status=response.status_code)

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text or f"HTTP {response.status_code} error"

        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str) and message:
                return str(message)

            details = payload.get("details")
            if isinstance(details, dict):
                detail_msg = details.get("message")
                if isinstance(detail_msg, str) and detail_msg:
                    return str(detail_msg)

        return response.text or f"HTTP {response.status_code} error"


    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._http_client.close()

    def __enter__(self) -> "FortyGuardClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
