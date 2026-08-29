"""Unit tests for Phase 15.2 Watchlist Evaluation Engine.

Verifies:
- Pure deterministic evaluation across all 6 criterion metrics.
- Temporal modes: PREVIOUS, FIRST, ROLLING.
- Anti-flapping hysteresis evaluation.
- Missing data distinction from zero (insufficient data reporting).
- Location and analysis type scope filtering.
- Immutability of input AnalysisRecord objects.
- Zero network I/O.
"""

from __future__ import annotations

from unittest.mock import patch
import pytest

from frontend.utils.clock import FrozenClock
from frontend.utils.watchlist_engine import (
    WatchlistEvaluation,
    evaluate_all_watchlists,
    evaluate_watchlist,
)
from frontend.utils.watchlists import Watchlist, WatchlistCriterion


class MockRecord:
    """Lightweight test AnalysisRecord simulator."""

    def __init__(
        self,
        analysis_id: str = "REC-01",
        analysis_type: str = "heatmap",
        location_label: str = "Downtown Core",
        date: str = "2026-08-20",
        created_at: str = "2026-08-20T10:00:00",
        metrics: dict | None = None,
        observed_temperature: float | None = None,
        status: str = "Completed",
    ):
        self.analysis_id = analysis_id
        self.analysis_type = analysis_type
        self.location_label = location_label
        self.date = date
        self.created_at = created_at
        self.metrics = dict(metrics) if metrics is not None else {}
        self.observed_temperature = observed_temperature
        self.status = status

    def to_dict(self) -> dict:
        return {
            "analysis_id": self.analysis_id,
            "analysis_type": self.analysis_type,
            "location_label": self.location_label,
            "date": self.date,
            "created_at": self.created_at,
            "metrics": dict(self.metrics),
            "observed_temperature": self.observed_temperature,
            "status": self.status,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 1. Static Criteria Metric Evaluations
# ══════════════════════════════════════════════════════════════════════════════


class TestStaticCriteriaEvaluation:
    """Evaluation of single-point metrics (mean_temp, spread, proportion, count)."""

    def test_mean_temperature_greater_than_matched(self):
        rec = MockRecord(metrics={"mean_temp": 39.5})
        wl = Watchlist(
            watchlist_id="WL-01",
            name="Heat Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=38.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True
        assert "mean_temperature" in res.matched_criteria
        assert res.observed_values["mean_temperature"] == 39.5
        assert len(res.evidence_list) >= 1

    def test_mean_temperature_not_matched(self):
        rec = MockRecord(metrics={"mean_temp": 36.0})
        wl = Watchlist(
            watchlist_id="WL-01",
            name="Heat Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=38.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is False
        assert "mean_temperature" in res.unmatched_criteria

    def test_temperature_spread_evaluation(self):
        rec = MockRecord(metrics={"temp_spread": 12.5})
        wl = Watchlist(
            watchlist_id="WL-02",
            name="Spread Watch",
            criteria=[WatchlistCriterion(metric="temperature_spread", operator=">", threshold=10.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True
        assert res.observed_values["temperature_spread"] == 12.5

    def test_above_threshold_proportion_normalized_percentage(self):
        # 0.45 decimal normalized to 45.0% when threshold is 40.0%
        rec = MockRecord(metrics={"above_threshold_proportion": 0.45})
        wl = Watchlist(
            watchlist_id="WL-03",
            name="Hot Area Watch",
            criteria=[WatchlistCriterion(metric="above_threshold_proportion", operator=">=", threshold=40.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True
        assert res.observed_values["above_threshold_proportion"] == 45.0

    def test_analysis_count_evaluation(self):
        recs = [MockRecord(analysis_id=f"R-{i}", date=f"2026-08-{i:02d}") for i in range(1, 6)]
        wl = Watchlist(
            watchlist_id="WL-04",
            name="Count Watch",
            criteria=[WatchlistCriterion(metric="analysis_count", operator=">=", threshold=5.0)],
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True
        assert res.observed_values["analysis_count"] == 5.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Temporal Comparison Modes (PREVIOUS, FIRST, ROLLING)
# ══════════════════════════════════════════════════════════════════════════════


class TestTemporalComparisonModes:
    """Temporal criteria evaluation across PREVIOUS, FIRST, and ROLLING baselines."""

    def _temporal_records(self) -> list[MockRecord]:
        return [
            MockRecord(analysis_id="R-1", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="R-2", date="2026-08-05", metrics={"mean_temp": 32.0}),
            MockRecord(analysis_id="R-3", date="2026-08-10", metrics={"mean_temp": 31.0}),
            MockRecord(analysis_id="R-4", date="2026-08-15", metrics={"mean_temp": 35.0}),
        ]

    def test_temperature_change_previous_mode(self):
        # Latest (R-4: 35.0°C) vs Previous (R-3: 31.0°C) -> Delta = +4.0°C
        recs = self._temporal_records()
        wl = Watchlist(
            watchlist_id="WL-TEMP-PREV",
            name="Warming Prev",
            criteria=[WatchlistCriterion(metric="temperature_change", operator=">=", threshold=3.0)],
            comparison_mode="PREVIOUS",
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True
        assert res.delta == 4.0
        assert res.baseline_analysis_id == "R-3"
        assert res.comparison_analysis_id == "R-4"

    def test_temperature_change_first_mode(self):
        # Latest (R-4: 35.0°C) vs First (R-1: 30.0°C) -> Delta = +5.0°C
        recs = self._temporal_records()
        wl = Watchlist(
            watchlist_id="WL-TEMP-FIRST",
            name="Warming First",
            criteria=[WatchlistCriterion(metric="temperature_change", operator=">=", threshold=4.5)],
            comparison_mode="FIRST",
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True
        assert res.delta == 5.0
        assert res.baseline_analysis_id == "R-1"
        assert res.comparison_analysis_id == "R-4"

    def test_temperature_change_rolling_mode(self):
        # Latest (R-4: 35.0°C) vs Rolling window of previous 3 (R-1: 30, R-2: 32, R-3: 31 -> avg: 31.0°C)
        # Delta = 35.0 - 31.0 = +4.0°C
        recs = self._temporal_records()
        wl = Watchlist(
            watchlist_id="WL-TEMP-ROLL",
            name="Warming Rolling",
            criteria=[WatchlistCriterion(metric="temperature_change", operator=">=", threshold=3.5)],
            comparison_mode="ROLLING",
            window_size=3,
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True
        assert res.delta == 4.0

    def test_temperature_change_percent_calculation(self):
        # Baseline: 30.0°C, Latest: 33.0°C -> +10.0%
        recs = [
            MockRecord(analysis_id="R-A", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="R-B", date="2026-08-02", metrics={"mean_temp": 33.0}),
        ]
        wl = Watchlist(
            watchlist_id="WL-PCT",
            name="Percent Rise",
            criteria=[WatchlistCriterion(metric="temperature_change_percent", operator=">=", threshold=8.0)],
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True
        assert res.percent_delta == 10.0


# ══════════════════════════════════════════════════════════════════════════════
# 3. Missing Data & Edge Case Handling
# ══════════════════════════════════════════════════════════════════════════════


class TestMissingDataAndEdgeCases:
    """Missing metrics, single record temporal evaluations, and empty states."""

    def test_single_record_temporal_change_reports_insufficient_data(self):
        # Single record cannot compute temporal change
        rec = MockRecord(analysis_id="R-SOLO", metrics={"mean_temp": 35.0})
        wl = Watchlist(
            watchlist_id="WL-SOLO",
            name="Temporal Change",
            criteria=[WatchlistCriterion(metric="temperature_change", operator=">", threshold=2.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is False
        assert "temperature_change" in res.insufficient_data_criteria
        assert res.data_quality in ("LOW", "INSUFFICIENT")
        assert len(res.limitations) >= 1

    def test_missing_metric_field_does_not_fabricate_zero(self):
        rec = MockRecord(analysis_id="R-NO-METRICS", metrics={})
        wl = Watchlist(
            watchlist_id="WL-MISSING",
            name="Missing Test",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=30.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is False
        assert "mean_temperature" in res.insufficient_data_criteria
        assert res.observed_values["mean_temperature"] is None

    def test_empty_record_list_evaluates_cleanly(self):
        wl = Watchlist(
            watchlist_id="WL-EMPTY",
            name="Empty Records Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0)],
        )
        res = evaluate_watchlist(wl, [])
        assert res.matched is False
        assert res.data_quality == "INSUFFICIENT"
        assert len(res.limitations) >= 1

    def test_disabled_watchlist_returns_not_matched(self):
        rec = MockRecord(metrics={"mean_temp": 45.0})
        wl = Watchlist(
            watchlist_id="WL-DISABLED",
            name="Disabled Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0)],
            enabled=False,
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is False
        assert "disabled" in res.limitations[0].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Scope Filtering & Multi-Criteria Matching
# ══════════════════════════════════════════════════════════════════════════════


class TestScopeAndMultiCriteriaMatching:
    """Scope filtering by location/analysis type and multi-criteria conjunction."""

    def test_location_scope_filtering(self):
        recs = [
            MockRecord(analysis_id="R-DT", location_label="Downtown Core", metrics={"mean_temp": 40.0}),
            MockRecord(analysis_id="R-HB", location_label="Harbor Point", metrics={"mean_temp": 30.0}),
        ]
        wl = Watchlist(
            watchlist_id="WL-LOC",
            name="Harbor Watch",
            location_scope="Harbor",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=35.0)],
        )
        # Harbor Point is 30.0°C < 35.0°C (Downtown Core is ignored)
        res = evaluate_watchlist(wl, recs)
        assert res.matched is False
        assert res.comparison_analysis_id == "R-HB"

    def test_multi_criteria_all_must_match(self):
        # Criterion 1: mean_temp >= 35.0 (True: 36.0)
        # Criterion 2: temp_spread >= 10.0 (False: 5.0)
        rec = MockRecord(metrics={"mean_temp": 36.0, "temp_spread": 5.0})
        wl = Watchlist(
            watchlist_id="WL-MULTI",
            name="Multi Condition",
            criteria=[
                WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=35.0),
                WatchlistCriterion(metric="temperature_spread", operator=">=", threshold=10.0),
            ],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is False
        assert "mean_temperature" in res.matched_criteria
        assert "temperature_spread" in res.unmatched_criteria

    def test_multi_criteria_all_matching_succeeds(self):
        rec = MockRecord(metrics={"mean_temp": 38.0, "temp_spread": 12.0})
        wl = Watchlist(
            watchlist_id="WL-MULTI-PASS",
            name="Multi Pass",
            criteria=[
                WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=35.0),
                WatchlistCriterion(metric="temperature_spread", operator=">=", threshold=10.0),
            ],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True
        assert len(res.matched_criteria) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 5. Immutability & Determinism Invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestEvaluationImmutabilityAndDeterminism:
    """Ensure records are strictly unmutated and evaluations are deterministic."""

    def test_records_not_mutated(self):
        original_metrics = {"mean_temp": 35.0, "temp_spread": 8.0}
        rec = MockRecord(metrics=dict(original_metrics))
        wl = Watchlist(
            watchlist_id="WL-IMMUTABLE",
            name="Immutability Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">", threshold=30.0)],
        )

        _ = evaluate_watchlist(wl, [rec])
        assert rec.metrics == original_metrics
        assert rec.metrics["mean_temp"] == 35.0

    def test_evaluate_all_watchlists_deterministic(self):
        clk = FrozenClock("2026-08-23T12:00:00")
        recs = [MockRecord(metrics={"mean_temp": 40.0})]
        wls = [
            Watchlist(watchlist_id="WL-1", name="W1", criteria=[WatchlistCriterion("mean_temperature", ">=", 38.0)]),
            Watchlist(watchlist_id="WL-2", name="W2", criteria=[WatchlistCriterion("mean_temperature", ">=", 42.0)]),
        ]

        run1 = evaluate_all_watchlists(wls, recs, clock=clk)
        run2 = evaluate_all_watchlists(wls, recs, clock=clk)

        assert len(run1) == 2
        assert run1[0].matched is True
        assert run1[1].matched is False
        assert run1[0].eval_id == run2[0].eval_id

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_evaluation_makes_zero_network_calls(self, mock_requests, mock_httpx):
        recs = [MockRecord(metrics={"mean_temp": 36.0})]
        wl = Watchlist(watchlist_id="WL-ZERO", name="Zero Net", criteria=[WatchlistCriterion("mean_temperature", ">", 30.0)])
        _ = evaluate_watchlist(wl, recs)

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

    def test_less_than_operator_matched(self):
        rec = MockRecord(metrics={"mean_temp": 28.0})
        wl = Watchlist(
            watchlist_id="WL-LT",
            name="Cool Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator="<", threshold=30.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True
        assert res.observed_values["mean_temperature"] == 28.0

    def test_less_than_or_equal_operator_matched(self):
        rec = MockRecord(metrics={"mean_temp": 30.0})
        wl = Watchlist(
            watchlist_id="WL-LTE",
            name="Cool Watch Exact",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator="<=", threshold=30.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True

    def test_equal_operator_matched_within_tolerance(self):
        rec = MockRecord(metrics={"mean_temp": 35.0})
        wl = Watchlist(
            watchlist_id="WL-EQ",
            name="Exact Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator="==", threshold=35.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True

    def test_not_equal_operator_matched(self):
        rec = MockRecord(metrics={"mean_temp": 35.2})
        wl = Watchlist(
            watchlist_id="WL-NEQ",
            name="Not Equal Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator="!=", threshold=35.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True

    def test_hysteresis_trigger_activation(self):
        # Trigger threshold: 38.0, Threshold: 37.0. Value 38.5 matches
        rec = MockRecord(metrics={"mean_temp": 38.5})
        wl = Watchlist(
            watchlist_id="WL-HYST",
            name="Hysteresis Watch",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=37.0, trigger_threshold=38.0, clear_threshold=36.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is True

    def test_hysteresis_trigger_below_activation_does_not_match(self):
        # Value 37.5 is above base threshold 37.0, but below trigger_threshold 38.0 -> does NOT activate
        rec = MockRecord(metrics={"mean_temp": 37.5})
        wl = Watchlist(
            watchlist_id="WL-HYST-OFF",
            name="Hysteresis Off",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=37.0, trigger_threshold=38.0, clear_threshold=36.0)],
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.matched is False

    def test_analysis_type_scope_filtering(self):
        recs = [
            MockRecord(analysis_id="R-HM", analysis_type="heatmap", metrics={"mean_temp": 40.0}),
            MockRecord(analysis_id="R-HI", analysis_type="heat_intelligence", observed_temperature=30.0),
        ]
        # Watchlist only targets Heat Intelligence
        wl = Watchlist(
            watchlist_id="WL-HI-ONLY",
            name="HI Only",
            analysis_type_scope="heat_intelligence",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=35.0)],
        )
        res = evaluate_watchlist(wl, recs)
        # HI analysis has 30.0°C < 35.0°C -> does not match
        assert res.matched is False
        assert res.comparison_analysis_id == "R-HI"

    def test_watchlist_evaluation_to_dict_and_from_dict_roundtrip(self):
        rec = MockRecord(metrics={"mean_temp": 42.0})
        wl = Watchlist(watchlist_id="WL-RT", name="Roundtrip", criteria=[WatchlistCriterion("mean_temperature", ">=", 40.0)])
        eval_res = evaluate_watchlist(wl, [rec])

        d = eval_res.to_dict()
        assert d["watchlist_id"] == "WL-RT"
        assert d["matched"] is True

        reconstructed = WatchlistEvaluation.from_dict(d)
        assert reconstructed.eval_id == eval_res.eval_id
        assert reconstructed.matched == eval_res.matched
        assert reconstructed.observed_values == eval_res.observed_values

    def test_non_causal_language_in_evidence_strings(self):
        forbidden_causal = ["caused by", "due to", "because of", "will cause", "forecast", "hazardous", "fatal"]
        recs = [
            MockRecord(analysis_id="R-1", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="R-2", date="2026-08-02", metrics={"mean_temp": 38.0}),
        ]
        wl = Watchlist(
            watchlist_id="WL-NOCM",
            name="Neutral Lang Watch",
            criteria=[
                WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=35.0),
                WatchlistCriterion(metric="temperature_change", operator=">=", threshold=5.0),
            ],
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True

        all_text = " ".join(res.evidence_list + res.limitations).lower()
        for word in forbidden_causal:
            assert word not in all_text, f"Forbidden term '{word}' found in evidence output."

    def test_zero_baseline_temperature_change_percent_handles_gracefully(self):
        recs = [
            MockRecord(analysis_id="R-ZERO", date="2026-08-01", metrics={"mean_temp": 0.0}),
            MockRecord(analysis_id="R-TWO", date="2026-08-02", metrics={"mean_temp": 5.0}),
        ]
        wl = Watchlist(
            watchlist_id="WL-ZERO-PCT",
            name="Zero Baseline",
            criteria=[WatchlistCriterion(metric="temperature_change_percent", operator=">", threshold=10.0)],
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is False
        assert "temperature_change_percent" in res.insufficient_data_criteria
        assert any("cannot compute percentage change" in lim for lim in res.limitations)

    def test_negative_temperature_decrease_matched(self):
        # Latest (28.0°C) vs Previous (35.0°C) -> Delta = -7.0°C
        recs = [
            MockRecord(analysis_id="R-HOT", date="2026-08-01", metrics={"mean_temp": 35.0}),
            MockRecord(analysis_id="R-COOL", date="2026-08-02", metrics={"mean_temp": 28.0}),
        ]
        wl = Watchlist(
            watchlist_id="WL-COOLING",
            name="Cooling Trend",
            criteria=[WatchlistCriterion(metric="temperature_change", operator="<=", threshold=-5.0)],
        )
        res = evaluate_watchlist(wl, recs)
        assert res.matched is True
        assert res.delta == -7.0

    def test_rolling_window_larger_than_available_history(self):
        # 3 records available, window_size=10 -> uses all available previous records
        recs = [
            MockRecord(analysis_id="R-1", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="R-2", date="2026-08-02", metrics={"mean_temp": 32.0}),
            MockRecord(analysis_id="R-3", date="2026-08-03", metrics={"mean_temp": 38.0}),
        ]
        wl = Watchlist(
            watchlist_id="WL-ROLL-LARGE",
            name="Large Window Rolling",
            criteria=[WatchlistCriterion(metric="temperature_change", operator=">", threshold=5.0)],
            comparison_mode="ROLLING",
            window_size=10,
        )
        res = evaluate_watchlist(wl, recs)
        # Baseline = (30 + 32) / 2 = 31.0°C. Delta = 38.0 - 31.0 = +7.0°C > 5.0°C
        assert res.matched is True
        assert res.delta == 7.0

    def test_evaluation_with_failed_analyses_ignores_non_completed(self):
        recs = [
            MockRecord(analysis_id="R-OK-1", date="2026-08-01", metrics={"mean_temp": 30.0}, status="Completed"),
            MockRecord(analysis_id="R-FAILED", date="2026-08-02", metrics={"mean_temp": 50.0}, status="Failed"),
            MockRecord(analysis_id="R-OK-2", date="2026-08-03", metrics={"mean_temp": 32.0}, status="Completed"),
        ]
        wl = Watchlist(
            watchlist_id="WL-IGNORE-FAILED",
            name="Ignore Failed",
            criteria=[WatchlistCriterion(metric="mean_temperature", operator=">=", threshold=45.0)],
        )
        res = evaluate_watchlist(wl, recs)
        # R-FAILED is ignored; latest completed is R-OK-2 (32.0°C < 45.0°C) -> does NOT match
        assert res.matched is False
        assert res.comparison_analysis_id == "R-OK-2"

    def test_watchlist_version_persisted_in_evaluation(self):
        rec = MockRecord(metrics={"mean_temp": 36.0})
        wl = Watchlist(
            watchlist_id="WL-V3",
            name="Version 3 Watch",
            criteria=[WatchlistCriterion("mean_temperature", ">=", 30.0)],
            version=3,
        )
        res = evaluate_watchlist(wl, [rec])
        assert res.watchlist_version == 3


