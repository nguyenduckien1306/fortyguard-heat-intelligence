"""Tests for FortyGuard heatmap client HTTP behavior (mocked)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from backend.api.exceptions import (
    AuthenticationError,
    ForbiddenError,
    InvalidRequestError,
    MalformedResponseError,
    NotFoundError,
    PollingTimeoutError,
    RateLimitError,
    ServerError,
)
from tests.conftest import (
    make_client,
    sample_heatmap_request,
    status_payload,
    submission_payload,
)


def test_successful_heatmap_submission() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.content
        assert request.headers["api-key"] == "test-key"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=submission_payload("heatmap-001"))

    client = make_client(handler)
    try:
        response = client.create_heatmap_request(sample_heatmap_request())
    finally:
        client.close()

    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/heatmap"
    assert response.activity_id == "heatmap-001"


def test_activity_id_extraction() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=submission_payload("extracted-id-42"))

    client = make_client(handler)
    try:
        response = client.create_heatmap_request(sample_heatmap_request())
    finally:
        client.close()

    assert response.activity_id == "extracted-id-42"


def test_processing_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/status/activity-123"
        return httpx.Response(200, json=status_payload(status="Processing"))

    client = make_client(handler)
    try:
        response = client.get_activity_status("activity-123")
    finally:
        client.close()

    assert response.status == "Processing"
    assert response.activity_id == "activity-123"
    assert response.result is None


def test_completed_status() -> None:
    result = {"heatmap_url": "https://example.com/heatmap.png"}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=status_payload(status="Completed", result=result),
        )

    client = make_client(handler)
    try:
        response = client.get_activity_status("activity-123")
    finally:
        client.close()

    assert response.status == "Completed"
    assert response.result == result


def test_failed_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload(status="Failed"))

    client = make_client(handler)
    try:
        response = client.get_activity_status("activity-123")
    finally:
        client.close()

    assert response.status == "Failed"


@patch("backend.api.client.time.sleep")
def test_poll_heatmap_result_completes(mock_sleep: object) -> None:
    responses = [
        httpx.Response(200, json=status_payload(status="Processing")),
        httpx.Response(
            200,
            json=status_payload(status="Completed", result={"tiles": []}),
        ),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    client = make_client(handler)
    try:
        result = client.poll_heatmap_result(
            "activity-123",
            max_attempts=5,
            poll_interval_seconds=0,
        )
    finally:
        client.close()

    assert result.status == "Completed"
    assert result.result == {"tiles": []}


@patch("backend.api.client.time.sleep")
def test_poll_heatmap_result_timeout(mock_sleep: object) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload(status="Processing"))

    client = make_client(handler)
    try:
        with pytest.raises(PollingTimeoutError) as exc_info:
            client.poll_heatmap_result(
                "activity-123",
                max_attempts=3,
                poll_interval_seconds=0,
            )
    finally:
        client.close()

    assert exc_info.value.activity_id == "activity-123"
    assert "timed out" in str(exc_info.value).lower()


@pytest.mark.parametrize("status_code", [400, 422])
def test_http_invalid_request(status_code: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"message": "Invalid request payload"},
        )

    client = make_client(handler)
    try:
        with pytest.raises(InvalidRequestError) as exc_info:
            client.create_heatmap_request(sample_heatmap_request())
    finally:
        client.close()

    assert exc_info.value.http_status == status_code


def test_http_401_authentication_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Invalid API key"})

    client = make_client(handler)
    try:
        with pytest.raises(AuthenticationError) as exc_info:
            client.get_activity_status("activity-123")
    finally:
        client.close()

    assert exc_info.value.http_status == 401


def test_http_403_forbidden_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Insufficient plan access"})

    client = make_client(handler)
    try:
        with pytest.raises(ForbiddenError) as exc_info:
            client.create_heatmap_request(sample_heatmap_request())
    finally:
        client.close()

    assert exc_info.value.http_status == 403


def test_http_404_not_found_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Activity not found"})

    client = make_client(handler)
    try:
        with pytest.raises(NotFoundError) as exc_info:
            client.get_activity_status("missing-id")
    finally:
        client.close()

    assert exc_info.value.http_status == 404


def test_http_429_rate_limit_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Rate limit exceeded"})

    client = make_client(handler)
    try:
        with pytest.raises(RateLimitError) as exc_info:
            client.create_heatmap_request(sample_heatmap_request())
    finally:
        client.close()

    assert exc_info.value.http_status == 429


def test_http_500_server_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "Internal server error"})

    client = make_client(handler)
    try:
        with pytest.raises(ServerError) as exc_info:
            client.get_activity_status("activity-123")
    finally:
        client.close()

    assert exc_info.value.http_status == 500


def test_missing_activity_id_in_submission_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": False,
                "status_code": 200,
                "message": "Heatmap Submitted Successfully",
                "data": {},
            },
        )

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError):
            client.create_heatmap_request(sample_heatmap_request())
    finally:
        client.close()


def test_malformed_status_response_missing_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": False,
                "status_code": 200,
                "message": "Processing",
                "data": {"activity_id": "activity-123"},
            },
        )

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError):
            client.get_activity_status("activity-123")
    finally:
        client.close()


def test_malformed_json_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError, match="non-JSON"):
            client.get_activity_status("activity-123")
    finally:
        client.close()


def test_status_activity_id_mismatch_is_malformed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=status_payload(activity_id="other-activity", status="Processing"),
        )

    client = make_client(handler)
    try:
        with pytest.raises(MalformedResponseError, match="different activity_id"):
            client.get_activity_status("activity-123")
    finally:
        client.close()


def test_poll_returns_immediate_completed_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=status_payload(status="Completed", result={"tiles": []}),
        )

    client = make_client(handler)
    try:
        result = client.poll_heatmap_result(
            "activity-123",
            max_attempts=5,
            poll_interval_seconds=0,
        )
    finally:
        client.close()

    assert result.status == "Completed"


def test_poll_stops_on_unknown_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload(status="Queued"))

    client = make_client(handler)
    try:
        result = client.poll_heatmap_result(
            "activity-123",
            max_attempts=5,
            poll_interval_seconds=0,
        )
    finally:
        client.close()

    assert result.status == "Queued"


@patch("backend.api.client.time.sleep")
def test_poll_stops_on_failed_status(mock_sleep: object) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status_payload(status="Failed"))

    client = make_client(handler)
    try:
        result = client.poll_heatmap_result(
            "activity-123",
            max_attempts=5,
            poll_interval_seconds=0,
        )
    finally:
        client.close()

    assert result.status == "Failed"
