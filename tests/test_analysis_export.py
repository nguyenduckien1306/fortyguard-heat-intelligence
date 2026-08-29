"""Tests for local analysis summary export utilities and security scrubbing."""

from __future__ import annotations

import json
from frontend.utils.export import (
    generate_analysis_export_dict,
    generate_analysis_export_json,
    generate_analysis_export_text,
    generate_analytical_brief,
    sanitize_raw_result_for_inspection,
)


_SAMPLE_ENTRY = {
    "analysis_type": "Heat Intelligence",
    "activity_id": "act-export-001",
    "status": "Completed",
    "label": "Test Location",
    "created_at": "2026-08-22 10:00:00",
    "updated_at": "2026-08-22 10:02:00",
    "request_params": {
        "latitude": 40.7050,
        "longitude": -74.0090,
        "temperature": 32.5,
        "date": "2024-07-15",
        "analysis": ["environmental", "urban"],
        "api_key": "MUST_BE_REMOVED",
        "download_link": "https://signed.s3.amazonaws.com/secret",
    },
    "metrics_summary": {
        "mean_temp": 32.5,
    },
}


def test_generate_analysis_export_dict_scrubs_secrets() -> None:
    data = generate_analysis_export_dict(_SAMPLE_ENTRY)
    assert data["analysis_type"] == "Heat Intelligence"
    assert data["activity_id"] == "act-export-001"
    req = data.get("request_parameters", {})
    # api_key and download_link should be redacted, not just absent
    assert req.get("latitude") == 40.7050
    json_str = json.dumps(data)
    assert "MUST_BE_REMOVED" not in json_str
    assert "s3.amazonaws.com" not in json_str


def test_generate_analysis_export_json() -> None:
    json_str = generate_analysis_export_json(_SAMPLE_ENTRY)
    parsed = json.loads(json_str)
    assert parsed["activity_id"] == "act-export-001"
    assert "MUST_BE_REMOVED" not in json_str
    assert "s3.amazonaws.com" not in json_str


def test_generate_analysis_export_text() -> None:
    txt_str = generate_analysis_export_text(_SAMPLE_ENTRY)
    assert "FORTYGUARD HEAT INTELLIGENCE" in txt_str
    assert "Activity ID   : act-export-001" in txt_str
    assert "MUST_BE_REMOVED" not in txt_str
    assert "s3.amazonaws.com" not in txt_str


def test_sanitize_raw_result_for_inspection() -> None:
    raw = {
        "download_link": "https://tos-dashboard-prod.s3.amazonaws.com/real-secret-key?token=123",
        "data": {"status": "ok"},
    }
    sanitized = sanitize_raw_result_for_inspection(raw)
    assert sanitized["download_link"] == "[REDACTED_SECURE_SIGNED_URL]"
    assert sanitized["data"] == {"status": "ok"}


# ── Phase 10: Recursive deep sanitization ──


def test_sanitize_nested_secrets() -> None:
    raw = {
        "metadata": {
            "download_link": "https://s3.amazonaws.com/signed",
            "nested": {
                "api_key": "secret-key-123",
                "normal_field": "safe value",
            },
        },
        "data": {"status": "ok"},
    }
    sanitized = sanitize_raw_result_for_inspection(raw)
    assert sanitized["metadata"]["download_link"] == "[REDACTED_SECURE_SIGNED_URL]"
    assert sanitized["metadata"]["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["metadata"]["nested"]["normal_field"] == "safe value"
    assert sanitized["data"]["status"] == "ok"


def test_sanitize_does_not_over_redact() -> None:
    raw = {
        "tokenizer": "standard",
        "tile_id": 42,
        "temperature": 32.5,
        "status": "completed",
    }
    sanitized = sanitize_raw_result_for_inspection(raw)
    # "tokenizer" should NOT be redacted — it's not a credential key
    assert sanitized["tokenizer"] == "standard"
    assert sanitized["tile_id"] == 42
    assert sanitized["temperature"] == 32.5


def test_sanitize_token_key_is_redacted() -> None:
    raw = {"token": "bearer-abc-123", "data": "ok"}
    sanitized = sanitize_raw_result_for_inspection(raw)
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["data"] == "ok"


def test_sanitize_authorization_key() -> None:
    raw = {"authorization": "Bearer xyz", "result": "fine"}
    sanitized = sanitize_raw_result_for_inspection(raw)
    assert sanitized["authorization"] == "[REDACTED]"


def test_sanitize_password_key() -> None:
    raw = {"password": "hunter2", "username": "admin"}
    sanitized = sanitize_raw_result_for_inspection(raw)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["username"] == "admin"


def test_sanitize_empty_and_none() -> None:
    assert sanitize_raw_result_for_inspection(None) == {}
    assert sanitize_raw_result_for_inspection({}) == {}


# ── Phase 10: Analytical brief ──


def test_generate_analytical_brief_basic() -> None:
    brief = generate_analytical_brief(_SAMPLE_ENTRY)
    assert "ANALYTICAL BRIEF" in brief
    assert "act-export-001" in brief
    assert "MUST_BE_REMOVED" not in brief
    assert "s3.amazonaws.com" not in brief


def test_generate_analytical_brief_with_insights() -> None:
    from frontend.utils.insights import Insight, InsightSeverity

    insights = [
        Insight(
            category="Test",
            title="Test Finding",
            severity=InsightSeverity.INFO,
            summary="Temperature is 32 °C.",
            evidence="mean = 32.0",
        )
    ]
    brief = generate_analytical_brief(_SAMPLE_ENTRY, insights=insights)
    assert "ANALYTICAL INSIGHTS" in brief
    assert "Test Finding" in brief
    assert "not additional FortyGuard classifications" in brief


def test_generate_analytical_brief_with_comparison() -> None:
    comparison = {
        "is_valid": True,
        "analysis_a_label": "Day 1",
        "analysis_b_label": "Day 2",
        "compared_metrics": [
            {
                "label": "Mean Temperature",
                "diff_formatted": "+1.50 °C",
                "interpretation": "Warmer in B",
            }
        ],
    }
    brief = generate_analytical_brief(_SAMPLE_ENTRY, comparison=comparison)
    assert "COMPARISON ANALYSIS" in brief
    assert "Warmer in B" in brief
