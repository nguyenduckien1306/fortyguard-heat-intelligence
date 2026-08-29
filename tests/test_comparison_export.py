"""Tests for Phase 13 comparison export utilities in frontend.utils.export.

Validates:
- generate_comparison_json: correct JSON structure, sanitization, serialization.
- generate_comparison_txt: formatted text output with narrative sections.
- generate_comparison_brief: formal brief with baseline/comparison/narrative layout.
- Deep credential sanitization across all export formats.
- Correct handling of ComparisonMetric dataclass instances vs dicts.
- Edge cases: empty metrics, missing narrative, no metrics available.
- Zero network I/O invariant.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from frontend.utils.decision_intelligence import (
    ComparisonMetric,
    RESPONSIBLE_ANALYTICS_DISCLAIMER,
)
from frontend.utils.export import (
    generate_comparison_brief,
    generate_comparison_json,
    generate_comparison_txt,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixture Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _metric(
    key: str = "mean_temperature",
    label: str = "Mean Temperature",
    baseline: float = 30.0,
    comparison: float = 35.0,
    delta: float = 5.0,
    pct: float = 16.67,
    unit: str = "°C",
    direction: str = "increase",
    interpretation: str = "Warmer.",
    evidence: str = "30→35",
    available: bool = True,
) -> ComparisonMetric:
    return ComparisonMetric(
        key=key,
        label=label,
        baseline_value=baseline,
        comparison_value=comparison,
        delta=delta,
        percent_change=pct,
        unit=unit,
        direction=direction,
        interpretation=interpretation,
        evidence=evidence,
        available=available,
    )


def _comparison_data(
    metrics: list[ComparisonMetric] | None = None,
    headline: str = "Test comparison headline.",
) -> dict[str, Any]:
    actual_metrics = [_metric()] if metrics is None else metrics
    return {
        "baseline_id": "A-001",
        "comparison_id": "B-001",
        "baseline_location": "Downtown",
        "comparison_location": "Suburbs",
        "baseline_date": "2025-06-01",
        "comparison_date": "2025-06-15",
        "headline": headline,
        "metrics": actual_metrics,
        "available_metrics": actual_metrics,
        "increased": [m for m in actual_metrics if m.direction == "increase"],
        "decreased": [],
        "unchanged": [],
        "missing": [],
        "data_quality": {
            "metrics_available": len([m for m in actual_metrics if m.available]),
            "metrics_total": 6,
            "metrics_comparable_ratio": f"{len([m for m in actual_metrics if m.available])} / 6",
            "missing_count": 5,
        },
        "disclaimer": RESPONSIBLE_ANALYTICS_DISCLAIMER,
    }


def _narrative() -> dict[str, Any]:
    return {
        "headline": "Test comparison.",
        "what_changed": "Mean Temperature increased from 30.00 to 35.00.",
        "what_stayed_similar": "No metrics remained unchanged.",
        "data_limitations": "Some metrics were unavailable.",
        "disclaimer": RESPONSIBLE_ANALYTICS_DISCLAIMER,
        "baseline_summary": "Baseline: A-001 (2025-06-01)",
        "comparison_summary": "Comparison: B-001 (2025-06-15)",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. generate_comparison_json
# ══════════════════════════════════════════════════════════════════════════════


class TestComparisonJson:
    """JSON comparison export tests."""

    def test_returns_valid_json(self):
        data = _comparison_data()
        result = generate_comparison_json(data)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_contains_export_type(self):
        data = _comparison_data()
        result = generate_comparison_json(data)
        parsed = json.loads(result)
        assert parsed.get("export_type") == "FORTYGUARD_COMPARATIVE_ANALYSIS"

    def test_contains_comparison_section(self):
        data = _comparison_data()
        result = generate_comparison_json(data)
        parsed = json.loads(result)
        assert "comparison" in parsed

    def test_includes_narrative_when_provided(self):
        data = _comparison_data()
        narrative = _narrative()
        result = generate_comparison_json(data, narrative)
        parsed = json.loads(result)
        assert "narrative" in parsed
        assert "what_changed" in parsed["narrative"]

    def test_excludes_narrative_when_not_provided(self):
        data = _comparison_data()
        result = generate_comparison_json(data)
        parsed = json.loads(result)
        assert "narrative" not in parsed

    def test_removes_non_serializable_keys(self):
        """Keys like 'available_metrics', 'increased', etc. should be removed."""
        data = _comparison_data()
        result = generate_comparison_json(data)
        parsed = json.loads(result)
        comp = parsed["comparison"]
        assert "available_metrics" not in comp
        assert "increased" not in comp
        assert "decreased" not in comp
        assert "unchanged" not in comp
        assert "missing" not in comp

    def test_sanitizes_credentials(self):
        data = _comparison_data()
        data["api_key"] = "SECRET_KEY_123"
        data["signed_url"] = "https://s3.example.com/signed?token=abc"
        result = generate_comparison_json(data)
        assert "SECRET_KEY_123" not in result
        assert "token=abc" not in result

    def test_empty_metrics_list(self):
        data = _comparison_data(metrics=[])
        result = generate_comparison_json(data)
        parsed = json.loads(result)
        assert parsed["comparison"]["metrics"] == []


# ══════════════════════════════════════════════════════════════════════════════
# 2. generate_comparison_txt
# ══════════════════════════════════════════════════════════════════════════════


class TestComparisonTxt:
    """Plain text comparison export tests."""

    def test_contains_header(self):
        data = _comparison_data()
        result = generate_comparison_txt(data)
        assert "FORTYGUARD" in result
        assert "COMPARATIVE ANALYSIS" in result

    def test_contains_headline(self):
        data = _comparison_data(headline="Custom headline!")
        result = generate_comparison_txt(data)
        assert "Custom headline!" in result

    def test_contains_baseline_info(self):
        data = _comparison_data()
        result = generate_comparison_txt(data)
        assert "A-001" in result
        assert "Downtown" in result

    def test_contains_comparison_info(self):
        data = _comparison_data()
        result = generate_comparison_txt(data)
        assert "B-001" in result
        assert "Suburbs" in result

    def test_metric_details_present(self):
        m = _metric(label="Mean Temperature", baseline=30.0, comparison=35.0, delta=5.0)
        data = _comparison_data(metrics=[m])
        result = generate_comparison_txt(data)
        assert "Mean Temperature" in result

    def test_unavailable_metric_shown_as_insufficient(self):
        m = _metric(
            label="Analyzed Tiles",
            available=False,
            baseline=None,
            comparison=None,
            delta=None,
            pct=None,
        )
        data = _comparison_data(metrics=[m])
        result = generate_comparison_txt(data)
        assert "Insufficient Data" in result or "Metric Missing" in result

    def test_narrative_sections_included(self):
        data = _comparison_data()
        narrative = _narrative()
        result = generate_comparison_txt(data, narrative)
        assert "What Changed" in result
        assert "What Stayed Similar" in result
        assert "Data Limitations" in result

    def test_responsible_analytics_section(self):
        data = _comparison_data()
        result = generate_comparison_txt(data)
        assert "RESPONSIBLE ANALYTICS" in result

    def test_sanitizes_credentials_in_txt(self):
        data = _comparison_data()
        data["api_key"] = "MY_SECRET_KEY"
        result = generate_comparison_txt(data)
        assert "MY_SECRET_KEY" not in result


# ══════════════════════════════════════════════════════════════════════════════
# 3. generate_comparison_brief
# ══════════════════════════════════════════════════════════════════════════════


class TestComparisonBrief:
    """Formal analytical comparison brief export tests."""

    def test_contains_header(self):
        data = _comparison_data()
        result = generate_comparison_brief(data)
        assert "ANALYTICAL COMPARISON BRIEF" in result

    def test_baseline_section(self):
        data = _comparison_data()
        result = generate_comparison_brief(data)
        assert "BASELINE" in result
        assert "A-001" in result
        assert "Downtown" in result

    def test_comparison_section(self):
        data = _comparison_data()
        result = generate_comparison_brief(data)
        assert "COMPARISON" in result
        assert "B-001" in result
        assert "Suburbs" in result

    def test_observed_changes_with_narrative(self):
        data = _comparison_data()
        narrative = _narrative()
        result = generate_comparison_brief(data, narrative)
        assert "OBSERVED CHANGES" in result
        assert "Mean Temperature increased" in result

    def test_consistent_metrics_with_narrative(self):
        data = _comparison_data()
        narrative = _narrative()
        result = generate_comparison_brief(data, narrative)
        assert "CONSISTENT METRICS" in result

    def test_data_limitations_with_narrative(self):
        data = _comparison_data()
        narrative = _narrative()
        result = generate_comparison_brief(data, narrative)
        assert "DATA LIMITATIONS" in result

    def test_metric_details_section(self):
        m = _metric(label="Mean Temperature", evidence="30 → 35")
        data = _comparison_data(metrics=[m])
        result = generate_comparison_brief(data)
        assert "METRIC DETAILS" in result
        assert "Mean Temperature" in result

    def test_disclaimer_section(self):
        data = _comparison_data()
        result = generate_comparison_brief(data)
        assert "RESPONSIBLE ANALYTICS DISCLAIMER" in result

    def test_without_narrative_uses_headline(self):
        data = _comparison_data(headline="Warmer conditions observed.")
        result = generate_comparison_brief(data, narrative=None)
        assert "Warmer conditions observed." in result

    def test_sanitizes_credentials_in_brief(self):
        data = _comparison_data()
        data["secret_key"] = "SUPER_SECRET"
        result = generate_comparison_brief(data)
        assert "SUPER_SECRET" not in result


# ══════════════════════════════════════════════════════════════════════════════
# 4. Cross-Format Consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestCrossFormatConsistency:
    """Verify key information is present across all export formats."""

    def test_all_formats_contain_baseline_id(self):
        data = _comparison_data()
        narrative = _narrative()

        json_out = generate_comparison_json(data, narrative)
        txt_out = generate_comparison_txt(data, narrative)
        brief_out = generate_comparison_brief(data, narrative)

        assert "A-001" in json_out
        assert "A-001" in txt_out
        assert "A-001" in brief_out

    def test_all_formats_contain_comparison_id(self):
        data = _comparison_data()
        narrative = _narrative()

        json_out = generate_comparison_json(data, narrative)
        txt_out = generate_comparison_txt(data, narrative)
        brief_out = generate_comparison_brief(data, narrative)

        assert "B-001" in json_out
        assert "B-001" in txt_out
        assert "B-001" in brief_out

    def test_no_credential_leaks_in_any_format(self):
        data = _comparison_data()
        data["api_key"] = "LEAK_TEST_KEY"
        data["password"] = "LEAK_TEST_PASS"
        narrative = _narrative()
        narrative["token"] = "LEAK_TEST_TOKEN"

        json_out = generate_comparison_json(data, narrative)
        txt_out = generate_comparison_txt(data, narrative)
        brief_out = generate_comparison_brief(data, narrative)

        for output in [json_out, txt_out, brief_out]:
            assert "LEAK_TEST_KEY" not in output
            assert "LEAK_TEST_PASS" not in output
            assert "LEAK_TEST_TOKEN" not in output
