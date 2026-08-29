"""Tests for local validation of the confirmed Heat Intelligence request and result models."""

import pytest
from pydantic import ValidationError

from backend.models.heat_intelligence import (
    HeatIntelligenceRequest,
    HeatIntelligenceSubmissionResponse,
    HeatIntelligenceSubmitAPIResponse,
)
from backend.models.heat_intelligence_result import (
    HeatIntelligenceResult,
    parse_heat_intelligence_result,
)
from tests.conftest import sample_heat_intelligence_request


def test_heat_intelligence_request_preserves_confirmed_shape() -> None:
    payload = sample_heat_intelligence_request().model_dump(mode="json")

    assert set(payload) == {"latitude", "longitude", "temperature", "date", "analysis"}
    assert payload["latitude"] == 40.7050
    assert payload["longitude"] == -74.0090
    assert payload["temperature"] == 32.5
    assert payload["date"] == "2024-07-15"
    assert payload["analysis"] == ["environmental", "urban"]


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.pop("latitude"),
        lambda value: value.pop("longitude"),
        lambda value: value.pop("temperature"),
        lambda value: value.pop("date"),
        lambda value: value.update({"latitude": 95.0}),  # > 90
        lambda value: value.update({"longitude": -190.0}), # < -180
        lambda value: value.update({"date": "invalid-date"}),
        lambda value: value.update({"analysis": []}),
        lambda value: value.update({"analysis": ["invalid_category"]}),
    ],
)
def test_heat_intelligence_request_rejects_structural_errors(change) -> None:
    payload = sample_heat_intelligence_request().model_dump(mode="json")
    change(payload)

    with pytest.raises(ValidationError):
        HeatIntelligenceRequest.model_validate(payload)


def test_heat_intelligence_response_models() -> None:
    sub = HeatIntelligenceSubmissionResponse(activity_id="hi-act-001")
    assert sub.activity_id == "hi-act-001"

    api_resp = HeatIntelligenceSubmitAPIResponse(activity_id="hi-act-002")
    assert api_resp.activity_id == "hi-act-002"
    assert "submitted successfully" in api_resp.message.lower()


def test_parse_heat_intelligence_confirmed_result() -> None:
    assert parse_heat_intelligence_result(None) is None

    confirmed_result = {
        "download_link": "https://tos-dashboard-prod.s3.amazonaws.com/data.pdf?sig=test"
    }
    parsed = parse_heat_intelligence_result(confirmed_result)
    assert parsed is not None
    assert parsed.download_link == "https://tos-dashboard-prod.s3.amazonaws.com/data.pdf?sig=test"
    assert parsed.raw == confirmed_result


def test_parse_heat_intelligence_result_fallback() -> None:
    raw_result = {
        "data": {"score": 88.5},
        "metadata": {"version": "1.0"},
    }
    parsed = parse_heat_intelligence_result(raw_result)
    assert parsed is not None
    assert parsed.download_link is None
    assert parsed.data == {"score": 88.5}
    assert parsed.metadata == {"version": "1.0"}
    assert parsed.raw == raw_result
