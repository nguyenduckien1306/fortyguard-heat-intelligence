"""Tests for confirmed Heat Intelligence real schema discovery and rendering."""

from __future__ import annotations

import httpx
import pytest

from backend.api.client import FortyGuardClient
from backend.api.exceptions import NotFoundError
from backend.models.heat_intelligence_result import parse_heat_intelligence_result
from frontend.components.heat_intelligence_result import render_heat_intelligence_result
from tests.conftest import make_client, sample_heat_intelligence_request
from tests.fixtures.heat_intelligence_results_real import (
    REAL_CONFIRMED_HEAT_INTELLIGENCE_RESULT,
    REAL_OBSERVED_404_RESPONSE,
)


def test_client_submits_to_confirmed_underscore_path() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json={"error": False, "data": {"activity_id": "hi-live-914"}})

    client = make_client(handler)
    try:
        response = client.create_heat_intelligence_request(sample_heat_intelligence_request())
    finally:
        client.close()

    assert captured["path"] == "/v1/heat_intelligence"
    assert captured["method"] == "POST"
    assert response.activity_id == "hi-live-914"


def test_client_handles_historical_404_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=REAL_OBSERVED_404_RESPONSE)

    client = make_client(handler)
    try:
        with pytest.raises(NotFoundError) as exc_info:
            client.create_heat_intelligence_request(sample_heat_intelligence_request())
    finally:
        client.close()

    assert exc_info.value.http_status == 404
    assert "Endpoint not found" in str(exc_info.value)


def test_parse_confirmed_real_completed_result() -> None:
    parsed = parse_heat_intelligence_result(REAL_CONFIRMED_HEAT_INTELLIGENCE_RESULT)
    assert parsed is not None
    assert parsed.download_link is not None
    assert "data.pdf" in parsed.download_link
    assert parsed.raw == REAL_CONFIRMED_HEAT_INTELLIGENCE_RESULT


def test_render_heat_intelligence_result_confirmed_schema() -> None:
    from streamlit.testing.v1 import AppTest

    def script():
        from frontend.components.heat_intelligence_result import render_heat_intelligence_result
        from tests.fixtures.heat_intelligence_results_real import REAL_CONFIRMED_HEAT_INTELLIGENCE_RESULT

        render_heat_intelligence_result(None, REAL_CONFIRMED_HEAT_INTELLIGENCE_RESULT)

    at = AppTest.from_function(script).run()
    assert not at.exception
    assert len(at.success) >= 1


def test_render_heat_intelligence_result_handles_none_safely() -> None:
    from streamlit.testing.v1 import AppTest

    def script():
        from frontend.components.heat_intelligence_result import render_heat_intelligence_result

        render_heat_intelligence_result(None, None)

    at = AppTest.from_function(script).run()
    assert not at.exception
    assert len(at.info) >= 1


def test_render_heat_intelligence_page_handles_404_error() -> None:
    from streamlit.testing.v1 import AppTest

    def script():
        from frontend.pages.heat_intelligence import render_heat_intelligence_page
        from frontend.services.api import BackendAPIClient, BackendAPIError

        class Mock404APIClient(BackendAPIClient):
            def submit_heat_intelligence(self, payload):
                raise BackendAPIError("Endpoint not found", status_code=404)

        client = Mock404APIClient()
        render_heat_intelligence_page(api_client=client)

    at = AppTest.from_function(script, default_timeout=20).run()
    assert not at.exception
