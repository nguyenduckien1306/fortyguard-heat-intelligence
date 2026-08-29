"""HTTP client for communicating with the FastAPI backend.

Streamlit must never call FortyGuard directly or hold API keys. All external
API access goes through the backend.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_API_BASE_URL = os.getenv("BACKEND_API_BASE_URL", "http://localhost:8000")


class BackendAPIError(Exception):
    """Safe, user-facing error from the FastAPI backend boundary."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BackendAPIClient:
    """Small client for the application's FastAPI backend."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_API_BASE_URL).rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
        )

    def fetch_health(self) -> dict[str, Any]:
        """GET /api/v1/health from the FastAPI backend."""
        return self._request_json("GET", "/api/v1/health")

    def submit_heatmap(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a documented heatmap request through FastAPI."""
        response = self._request_json("POST", "/api/v1/heatmap/", json=payload)
        activity_id = response.get("activity_id")
        if not isinstance(activity_id, str) or not activity_id.strip():
            raise BackendAPIError("The backend returned no activity ID.")
        return response

    def get_heatmap_status(self, activity_id: str) -> dict[str, Any]:
        """GET the current activity status through FastAPI."""
        self._validate_activity_id(activity_id)
        encoded_id = quote(activity_id, safe="")
        return self._request_json(
            "GET",
            f"/api/v1/heatmap/status/{encoded_id}",
        )

    def poll_heatmap(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        """Ask FastAPI to perform its bounded server-side polling workflow."""
        self._validate_activity_id(activity_id)
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must not be negative")
        encoded_id = quote(activity_id, safe="")
        return self._request_json(
            "GET",
            f"/api/v1/heatmap/status/{encoded_id}/poll",
            params={
                "max_attempts": max_attempts,
                "poll_interval_seconds": poll_interval_seconds,
            },
        )

    def submit_heat_intelligence(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a documented Heat Intelligence request through FastAPI."""
        response = self._request_json("POST", "/api/v1/heat-intelligence/", json=payload)
        activity_id = response.get("activity_id")
        if not isinstance(activity_id, str) or not activity_id.strip():
            raise BackendAPIError("The backend returned no activity ID.")
        return response

    def get_heat_intelligence_status(self, activity_id: str) -> dict[str, Any]:
        """GET current Heat Intelligence activity status through FastAPI."""
        self._validate_activity_id(activity_id)
        encoded_id = quote(activity_id, safe="")
        return self._request_json(
            "GET",
            f"/api/v1/heat-intelligence/status/{encoded_id}",
        )

    def poll_heat_intelligence(
        self,
        activity_id: str,
        *,
        max_attempts: int = 30,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        """Ask FastAPI to perform server-side bounded polling for Heat Intelligence."""
        self._validate_activity_id(activity_id)
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must not be negative")
        encoded_id = quote(activity_id, safe="")
        return self._request_json(
            "GET",
            f"/api/v1/heat-intelligence/status/{encoded_id}/poll",
            params={
                "max_attempts": max_attempts,
                "poll_interval_seconds": poll_interval_seconds,
            },
        )

    def download_heat_intelligence_report(self, activity_id: str) -> bytes:
        """Download the Heat Intelligence PDF report via the backend proxy.

        Returns raw PDF bytes. The signed S3 URL is never exposed to the frontend.
        """
        self._validate_activity_id(activity_id)
        encoded_id = quote(activity_id, safe="")
        try:
            response = self._client.get(
                f"/api/v1/heat-intelligence/report/{encoded_id}",
                timeout=120.0,
            )
        except httpx.HTTPError as exc:
            raise BackendAPIError("Unable to reach the FastAPI backend.") from exc

        if response.status_code >= 400:
            # Try to extract JSON detail
            try:
                payload = response.json()
                detail = payload.get("detail", "")
            except (ValueError, AttributeError):
                detail = ""
            message = detail if detail else f"Report download failed ({response.status_code})."
            raise BackendAPIError(message, status_code=response.status_code)

        if not response.content:
            raise BackendAPIError("The backend returned an empty report.", status_code=204)

        return response.content


    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                path,
                json=json,
                params=params,
            )
        except httpx.HTTPError as exc:
            raise BackendAPIError("Unable to reach the FastAPI backend.") from exc

        payload = self._decode_response(response)
        if not isinstance(payload, dict):
            raise BackendAPIError(
                "The backend returned an invalid response.",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            detail = payload.get("detail")
            message = detail if isinstance(detail, str) else self._status_message(response)
            raise BackendAPIError(message, status_code=response.status_code)

        return payload

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise BackendAPIError(
                "The backend returned an invalid JSON response.",
                status_code=response.status_code,
            ) from exc

    @staticmethod
    def _status_message(response: httpx.Response) -> str:
        reason = response.reason_phrase or "request failed"
        return f"Backend request failed ({response.status_code}: {reason})."

    @staticmethod
    def _validate_activity_id(activity_id: str) -> None:
        if not activity_id.strip():
            raise ValueError("activity_id must not be empty")

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this instance."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "BackendAPIClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def fetch_health(base_url: str | None = None) -> dict[str, Any]:
    """Convenience helper to fetch backend health without managing a client."""
    with BackendAPIClient(base_url=base_url) as client:
        return client.fetch_health()
