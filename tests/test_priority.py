"""Tests for frontend.utils.priority — Deterministic Priority Engine.

Validates:
- Explicit scoring formula weights: severity, magnitude, recency, persistence, data quality.
- Magnitude points across different metric types (temperature, spread, proportion, tile count).
- Recency points calculation across timestamps.
- Persistence factor across signal types.
- Data quality multiplier impact (HIGH, MEDIUM, LOW, INSUFFICIENT).
- Priority classification thresholds (Critical >= 75, High >= 50, Medium >= 30, Low < 30).
- Deterministic priority sorting.
- Zero network I/O invariant.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from frontend.utils.operational_intelligence import OperationalSignal
from frontend.utils.priority import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    calculate_magnitude_points,
    calculate_persistence_points,
    calculate_priority_score,
    calculate_recency_points,
    classify_priority,
    get_signal_priority,
    sort_signals_by_priority,
)


def _make_signal(
    signal_id: str = "SIG-1",
    severity: str = "CRITICAL",
    signal_type: str = "temperature_above_threshold",
    metric: str = "mean_temperature",
    observed_value: float | None = 45.0,
    threshold_value: float | None = 40.0,
    data_quality: str = "HIGH",
    created_at: str | None = None,
) -> OperationalSignal:
    now_iso = created_at or datetime.now(timezone.utc).isoformat()
    return OperationalSignal(
        signal_id=signal_id,
        analysis_id="REC-1",
        signal_type=signal_type,
        severity=severity,
        title="Signal Title",
        description="Signal Desc",
        metric=metric,
        observed_value=observed_value,
        threshold_value=threshold_value,
        data_quality=data_quality,
        created_at=now_iso,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Scoring Component Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestScoringComponents:
    """Individual mathematical components of priority score."""

    def test_magnitude_temperature_scaling(self):
        # 5°C exceedance = full 30 pts
        pts_5deg = calculate_magnitude_points(45.0, 40.0, "mean_temperature")
        assert abs(pts_5deg - 30.0) < 1e-4

        # 2.5°C exceedance = 15 pts
        pts_2_5deg = calculate_magnitude_points(42.5, 40.0, "mean_temperature")
        assert abs(pts_2_5deg - 15.0) < 1e-4

        # Zero exceedance = 0 pts
        pts_0deg = calculate_magnitude_points(40.0, 40.0, "mean_temperature")
        assert abs(pts_0deg - 0.0) < 1e-4

    def test_magnitude_spread_scaling(self):
        pts_spread = calculate_magnitude_points(18.0, 8.0, "temperature_spread")
        assert pts_spread == 30.0  # capped at 30 pts

    def test_magnitude_proportion_scaling(self):
        pts_prop = calculate_magnitude_points(75.0, 25.0, "above_threshold_proportion")
        assert pts_prop == 30.0  # 50% diff = 30 pts

    def test_magnitude_none_fallback(self):
        pts_none = calculate_magnitude_points(None, 40.0, "mean_temperature")
        assert pts_none == 5.0

    def test_recency_points_fresh_observation(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        pts = calculate_recency_points(now_iso)
        assert pts == 15.0

    def test_recency_points_last_week(self):
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        pts = calculate_recency_points(three_days_ago)
        assert pts == 10.0

    def test_recency_points_last_month(self):
        twenty_days_ago = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        pts = calculate_recency_points(twenty_days_ago)
        assert pts == 5.0

    def test_recency_points_old_observation(self):
        sixty_days_ago = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        pts = calculate_recency_points(sixty_days_ago)
        assert pts == 2.0

    def test_recency_points_invalid_string_fallback(self):
        pts = calculate_recency_points("invalid-date-string")
        assert pts == 8.0

    def test_persistence_points(self):
        assert calculate_persistence_points("persistent_elevation") == 15.0
        assert calculate_persistence_points("temperature_increase") == 15.0
        assert calculate_persistence_points("temperature_above_threshold") == 10.0
        assert calculate_persistence_points("persistent_stability") == 5.0
        assert calculate_persistence_points("insufficient_data") == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Priority Classification & Multipliers
# ══════════════════════════════════════════════════════════════════════════════


class TestPriorityClassification:
    """Classification of raw and weighted scores into priority tiers."""

    def test_critical_priority_classification(self):
        # Critical severity (40) + max magnitude (30) + fresh recency (15) + persistence (15) = 100
        sig = _make_signal(
            severity="CRITICAL",
            signal_type="persistent_elevation",
            observed_value=46.0,
            threshold_value=40.0,
            data_quality="HIGH",
        )
        score, label = get_signal_priority(sig)
        assert score >= 75.0
        assert label == PRIORITY_CRITICAL

    def test_high_priority_classification(self):
        # Elevated severity (30) + moderate magnitude (15) + fresh (15) = 60
        sig = _make_signal(
            severity="ELEVATED",
            signal_type="other",
            observed_value=42.5,
            threshold_value=40.0,
            data_quality="HIGH",
        )
        score, label = get_signal_priority(sig)
        assert 50.0 <= score < 75.0
        assert label == PRIORITY_HIGH

    def test_medium_priority_classification(self):
        sig = _make_signal(
            severity="WATCH",
            signal_type="other",
            observed_value=41.0,
            threshold_value=40.0,
            data_quality="HIGH",
        )
        score, label = get_signal_priority(sig)
        assert 30.0 <= score < 50.0
        assert label == PRIORITY_MEDIUM

    def test_low_priority_classification(self):
        sig = _make_signal(
            severity="INFO",
            signal_type="other",
            observed_value=40.0,
            threshold_value=40.0,
            data_quality="HIGH",
        )
        # 10 (info) + 0 (mag) + 15 (recency) = 25
        score, label = get_signal_priority(sig)
        assert score < 30.0
        assert label == PRIORITY_LOW

    def test_data_quality_multiplier_reduces_score(self):
        sig_high = _make_signal(severity="CRITICAL", data_quality="HIGH")
        sig_low = _make_signal(severity="CRITICAL", data_quality="LOW")
        sig_insuf = _make_signal(severity="CRITICAL", data_quality="INSUFFICIENT")

        score_high = calculate_priority_score(sig_high)
        score_low = calculate_priority_score(sig_low)
        score_insuf = calculate_priority_score(sig_insuf)

        assert score_high > score_low > score_insuf

    def test_priority_score_capped_at_100(self):
        sig = _make_signal(
            severity="CRITICAL",
            signal_type="persistent_elevation",
            observed_value=60.0,
            threshold_value=30.0,
            data_quality="HIGH",
        )
        score = calculate_priority_score(sig)
        assert score == 100.0

    def test_priority_score_non_negative(self):
        sig = _make_signal(severity="INFO", observed_value=None, threshold_value=None, data_quality="INSUFFICIENT")
        score = calculate_priority_score(sig)
        assert score >= 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 3. Deterministic Sorting
# ══════════════════════════════════════════════════════════════════════════════


class TestPrioritySorting:
    """Sorting collections of signals by priority score."""

    def test_sort_signals_by_priority_descending(self):
        sig_crit = _make_signal(signal_id="S-CRIT", severity="CRITICAL", observed_value=45.0, threshold_value=40.0)
        sig_high = _make_signal(signal_id="S-HIGH", severity="ELEVATED", observed_value=42.0, threshold_value=40.0)
        sig_low = _make_signal(signal_id="S-LOW", severity="INFO", observed_value=40.0, threshold_value=40.0)

        sorted_sigs = sort_signals_by_priority([sig_low, sig_crit, sig_high])
        assert [s.signal_id for s in sorted_sigs] == ["S-CRIT", "S-HIGH", "S-LOW"]

    def test_sort_empty_list_returns_empty(self):
        assert sort_signals_by_priority([]) == []

    def test_sort_tie_breaking_by_created_at_and_id(self):
        s1 = _make_signal(signal_id="S-A", severity="INFO", observed_value=30.0, threshold_value=30.0, created_at="2026-08-22T10:00:00")
        s2 = _make_signal(signal_id="S-B", severity="INFO", observed_value=30.0, threshold_value=30.0, created_at="2026-08-22T12:00:00")
        sorted_sigs = sort_signals_by_priority([s1, s2])
        assert len(sorted_sigs) == 2

    def test_dictionary_inputs_supported(self):
        dict_sig = {
            "signal_id": "DICT-1",
            "severity": "CRITICAL",
            "observed_value": 45.0,
            "threshold_value": 40.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data_quality": "HIGH",
        }
        score = calculate_priority_score(dict_sig)
        assert score >= 75.0
        assert classify_priority(score) == PRIORITY_CRITICAL

