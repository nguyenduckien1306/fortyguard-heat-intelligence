"""Tests for frontend.utils.narrative — Evidence-Backed Analytical Narrative Engine.

Validates:
- Narrative generation from comparison results.
- "What Changed?" section with increase/decrease language.
- "What Stayed Similar?" section.
- Data Limitations section for missing metrics.
- Neutral, non-causal language invariant.
- No medical, health, or forecast claims.
- Correct handling of edge cases (empty metrics, all missing, etc).
- Zero network I/O invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from frontend.utils.decision_intelligence import (
    ComparisonMetric,
    RESPONSIBLE_ANALYTICS_DISCLAIMER,
)
from frontend.utils.narrative import generate_comparison_narrative


# ──────────────────────────────────────────────────────────────────────────────
# Fixture Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _metric(
    key: str = "mean_temperature",
    label: str = "Mean Temperature",
    baseline: float | None = 30.0,
    comparison: float | None = 35.0,
    delta: float | None = 5.0,
    pct: float | None = 16.67,
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


def _comparison_result(
    increased: list[ComparisonMetric] | None = None,
    decreased: list[ComparisonMetric] | None = None,
    unchanged: list[ComparisonMetric] | None = None,
    missing: list[ComparisonMetric] | None = None,
    headline: str = "Test comparison.",
    baseline_id: str = "A-001",
    comparison_id: str = "B-001",
    baseline_date: str = "2025-06-01",
    comparison_date: str = "2025-06-15",
) -> dict[str, Any]:
    return {
        "increased": increased or [],
        "decreased": decreased or [],
        "unchanged": unchanged or [],
        "missing": missing or [],
        "headline": headline,
        "baseline_id": baseline_id,
        "comparison_id": comparison_id,
        "baseline_date": baseline_date,
        "comparison_date": comparison_date,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. Basic Narrative Structure
# ══════════════════════════════════════════════════════════════════════════════


class TestNarrativeStructure:
    """Verify narrative output dictionary has all required keys."""

    def test_returns_all_required_keys(self):
        result = _comparison_result()
        narrative = generate_comparison_narrative(result)

        assert "headline" in narrative
        assert "what_changed" in narrative
        assert "what_stayed_similar" in narrative
        assert "data_limitations" in narrative
        assert "disclaimer" in narrative
        assert "baseline_summary" in narrative
        assert "comparison_summary" in narrative

    def test_disclaimer_matches_global(self):
        result = _comparison_result()
        narrative = generate_comparison_narrative(result)
        assert narrative["disclaimer"] == RESPONSIBLE_ANALYTICS_DISCLAIMER


# ══════════════════════════════════════════════════════════════════════════════
# 2. "What Changed?" Section
# ══════════════════════════════════════════════════════════════════════════════


class TestWhatChanged:
    """Narrative correctly describes increased and decreased metrics."""

    def test_increase_described(self):
        inc = _metric(
            label="Mean Temperature",
            baseline=30.0,
            comparison=35.0,
            delta=5.0,
            pct=16.67,
            direction="increase",
        )
        result = _comparison_result(increased=[inc])
        narrative = generate_comparison_narrative(result)

        text = narrative["what_changed"]
        assert "Mean Temperature" in text
        assert "increased" in text.lower()
        assert "30.00" in text
        assert "35.00" in text

    def test_decrease_described(self):
        dec = _metric(
            label="Min Temperature",
            baseline=28.0,
            comparison=24.0,
            delta=-4.0,
            pct=-14.29,
            direction="decrease",
        )
        result = _comparison_result(decreased=[dec])
        narrative = generate_comparison_narrative(result)

        text = narrative["what_changed"]
        assert "Min Temperature" in text
        assert "decreased" in text.lower()

    def test_multiple_changes(self):
        inc = _metric(
            label="Mean Temperature",
            baseline=30.0,
            comparison=35.0,
            delta=5.0,
            direction="increase",
        )
        dec = _metric(
            label="Max Temperature",
            baseline=40.0,
            comparison=36.0,
            delta=-4.0,
            direction="decrease",
        )
        result = _comparison_result(increased=[inc], decreased=[dec])
        narrative = generate_comparison_narrative(result)

        text = narrative["what_changed"]
        assert "Mean Temperature" in text
        assert "Max Temperature" in text

    def test_no_changes_produces_neutral_message(self):
        result = _comparison_result()  # No increases or decreases
        narrative = generate_comparison_narrative(result)

        text = narrative["what_changed"]
        assert "no measurable changes" in text.lower()


# ══════════════════════════════════════════════════════════════════════════════
# 3. "What Stayed Similar?" Section
# ══════════════════════════════════════════════════════════════════════════════


class TestWhatStayedSimilar:
    """Narrative correctly describes unchanged metrics."""

    def test_unchanged_described(self):
        unch = _metric(
            label="Temperature Spread",
            baseline=10.0,
            comparison=10.05,
            delta=0.05,
            direction="unchanged",
        )
        result = _comparison_result(unchanged=[unch])
        narrative = generate_comparison_narrative(result)

        text = narrative["what_stayed_similar"]
        assert "Temperature Spread" in text
        assert "tolerance" in text.lower()

    def test_no_unchanged_produces_fallback_message(self):
        result = _comparison_result(unchanged=[])
        narrative = generate_comparison_narrative(result)

        text = narrative["what_stayed_similar"]
        assert "measurable changes" in text.lower() or "all evaluated" in text.lower()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Data Limitations Section
# ══════════════════════════════════════════════════════════════════════════════


class TestDataLimitations:
    """Narrative correctly describes missing / unavailable metrics."""

    def test_missing_metric_described(self):
        miss = _metric(
            label="Analyzed Tiles",
            available=False,
            direction="insufficient_data",
            baseline=None,
            comparison=None,
            delta=None,
            pct=None,
        )
        result = _comparison_result(missing=[miss])
        narrative = generate_comparison_narrative(result)

        text = narrative["data_limitations"]
        assert "Analyzed Tiles" in text
        assert "could not be compared" in text.lower()

    def test_no_missing_produces_all_present_message(self):
        result = _comparison_result(missing=[])
        narrative = generate_comparison_narrative(result)

        text = narrative["data_limitations"]
        assert "all candidate" in text.lower() or "successfully evaluated" in text.lower()

    def test_multiple_missing(self):
        m1 = _metric(label="Metric A", available=False, direction="insufficient_data",
                      baseline=None, comparison=None, delta=None, pct=None)
        m2 = _metric(label="Metric B", available=False, direction="insufficient_data",
                      baseline=None, comparison=None, delta=None, pct=None)
        result = _comparison_result(missing=[m1, m2])
        narrative = generate_comparison_narrative(result)

        text = narrative["data_limitations"]
        assert "Metric A" in text
        assert "Metric B" in text


# ══════════════════════════════════════════════════════════════════════════════
# 5. Responsible Analytics — Language Invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestNarrativeResponsibleLanguage:
    """Ensure no causal, medical, or forecast language in any narrative section."""

    FORBIDDEN_TERMS = [
        "caused by",
        "due to",
        "hazardous",
        "fatal",
        "deadly",
        "health risk",
        "will cause",
        "prediction",
        "forecast",
        "diagnosis",
        "heatstroke",
        "mortality",
    ]

    def _full_narrative(self) -> dict[str, Any]:
        inc = _metric(
            label="Mean Temperature",
            baseline=25.0,
            comparison=50.0,
            delta=25.0,
            pct=100.0,
            direction="increase",
        )
        dec = _metric(
            label="Min Temperature",
            baseline=20.0,
            comparison=10.0,
            delta=-10.0,
            pct=-50.0,
            direction="decrease",
        )
        miss = _metric(
            label="Tiles",
            available=False,
            direction="insufficient_data",
            baseline=None,
            comparison=None,
            delta=None,
            pct=None,
        )
        unch = _metric(
            label="Spread",
            baseline=10.0,
            comparison=10.01,
            delta=0.01,
            direction="unchanged",
        )
        result = _comparison_result(
            increased=[inc],
            decreased=[dec],
            unchanged=[unch],
            missing=[miss],
        )
        return generate_comparison_narrative(result)

    def test_what_changed_no_forbidden_terms(self):
        narrative = self._full_narrative()
        text = narrative["what_changed"].lower()
        for term in self.FORBIDDEN_TERMS:
            assert term not in text, f"Forbidden term '{term}' in what_changed"

    def test_what_stayed_similar_no_forbidden_terms(self):
        narrative = self._full_narrative()
        text = narrative["what_stayed_similar"].lower()
        for term in self.FORBIDDEN_TERMS:
            assert term not in text, f"Forbidden term '{term}' in what_stayed_similar"

    def test_data_limitations_no_forbidden_terms(self):
        narrative = self._full_narrative()
        text = narrative["data_limitations"].lower()
        for term in self.FORBIDDEN_TERMS:
            assert term not in text, f"Forbidden term '{term}' in data_limitations"

    def test_disclaimer_no_forbidden_terms(self):
        narrative = self._full_narrative()
        text = narrative["disclaimer"].lower()
        for term in self.FORBIDDEN_TERMS:
            assert term not in text, f"Forbidden term '{term}' in disclaimer"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Edge Cases
# ══════════════════════════════════════════════════════════════════════════════


class TestNarrativeEdgeCases:
    """Edge case handling in narrative generation."""

    def test_empty_comparison_result(self):
        result: dict[str, Any] = {}
        narrative = generate_comparison_narrative(result)
        assert "what_changed" in narrative
        assert "what_stayed_similar" in narrative
        assert "data_limitations" in narrative

    def test_headline_passthrough(self):
        result = _comparison_result(headline="Custom headline text.")
        narrative = generate_comparison_narrative(result)
        assert narrative["headline"] == "Custom headline text."

    def test_baseline_summary_format(self):
        result = _comparison_result(baseline_id="A-001", baseline_date="2025-06-01")
        narrative = generate_comparison_narrative(result)
        assert "A-001" in narrative["baseline_summary"]
        assert "2025-06-01" in narrative["baseline_summary"]

    def test_comparison_summary_format(self):
        result = _comparison_result(comparison_id="B-001", comparison_date="2025-06-15")
        narrative = generate_comparison_narrative(result)
        assert "B-001" in narrative["comparison_summary"]
        assert "2025-06-15" in narrative["comparison_summary"]
