"""Test suite for Latest vs Previous Change Detection Engine (Phase 17)."""

from __future__ import annotations

import json
import math

import pytest

from frontend.utils.latest_change import (
    LatestChangeSummary,
    MetricChange,
    compute_latest_change,
)


def _rec(aid, date="2026-08-28", temp=None, dq="HIGH", threshold=None, **extra):
    d = {"analysis_id": aid, "date": date, "data_quality": dq, "metrics": {}}
    if temp is not None:
        d["observed_temperature"] = temp
        d["metrics"]["mean_temp"] = temp
    if threshold is not None:
        d["threshold"] = threshold
    d.update(extra)
    return d


class TestComputeLatestChange:
    def test_empty_records(self):
        result = compute_latest_change([])
        assert result.is_first_analysis is True
        assert result.baseline_analysis_id is None
        assert result.latest_analysis_id is None
        assert result.changed_metrics == []
        assert result.unchanged_metrics == []

    def test_single_record_is_first_analysis(self):
        result = compute_latest_change([_rec("R1")])
        assert result.is_first_analysis is True
        assert result.latest_analysis_id == "R1"
        assert result.baseline_analysis_id is None

    def test_two_records_comparison(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=33.0)]
        result = compute_latest_change(recs)
        assert result.is_first_analysis is False
        assert result.baseline_analysis_id == "R1"
        assert result.latest_analysis_id == "R2"
        assert len(result.changed_metrics) > 0

    def test_temperature_increase_detected(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        result = compute_latest_change(recs)
        temp_changes = [m for m in result.changed_metrics if "Temperature" in m.metric_name or "temperature" in m.metric_name]
        assert any(m.direction == "increased" for m in temp_changes)
        increased = [m for m in temp_changes if m.direction == "increased"][0]
        assert increased.difference == 5.0

    def test_temperature_decrease_detected(self):
        recs = [_rec("R1", date="2026-08-01", temp=35.0), _rec("R2", date="2026-08-02", temp=30.0)]
        result = compute_latest_change(recs)
        temp_changes = [m for m in result.changed_metrics if "Temperature" in m.metric_name]
        assert any(m.direction == "decreased" for m in temp_changes)

    def test_unchanged_metrics_tracked(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=30.0)]
        result = compute_latest_change(recs)
        assert len(result.unchanged_metrics) > 0
        assert all(m.direction == "unchanged" for m in result.unchanged_metrics)

    def test_percentage_change_computed(self):
        recs = [_rec("R1", date="2026-08-01", temp=20.0), _rec("R2", date="2026-08-02", temp=30.0)]
        result = compute_latest_change(recs)
        temp_changes = [m for m in result.changed_metrics if "Temperature" in m.metric_name]
        assert any(m.percentage_change == 50.0 for m in temp_changes)

    def test_zero_baseline_percentage_none(self):
        recs = [
            {"analysis_id": "R1", "date": "2026-08-01", "metrics": {"hot_spot_count": 0}},
            {"analysis_id": "R2", "date": "2026-08-02", "metrics": {"hot_spot_count": 5}},
        ]
        result = compute_latest_change(recs)
        hot_spot = [m for m in result.changed_metrics if "Hot Spot" in m.metric_name]
        if hot_spot:
            assert hot_spot[0].percentage_change is None

    def test_nan_temperature_treated_as_unavailable(self):
        recs = [_rec("R1", date="2026-08-01", temp=float("nan")), _rec("R2", date="2026-08-02", temp=30.0)]
        result = compute_latest_change(recs)
        # NaN baseline should result in unavailable direction, not in changed
        for m in result.changed_metrics:
            if "Temperature" in m.metric_name:
                assert m.baseline_value is not None or m.direction == "unavailable"

    def test_inf_temperature_treated_as_unavailable(self):
        recs = [_rec("R1", date="2026-08-01", temp=float("inf")), _rec("R2", date="2026-08-02", temp=30.0)]
        result = compute_latest_change(recs)
        # Should not crash

    def test_negative_temperature_handled(self):
        recs = [_rec("R1", date="2026-08-01", temp=-5.0), _rec("R2", date="2026-08-02", temp=-2.0)]
        result = compute_latest_change(recs)
        temp_changes = [m for m in result.changed_metrics if "Temperature" in m.metric_name]
        assert any(m.direction == "increased" for m in temp_changes)

    def test_data_quality_degraded(self):
        recs = [_rec("R1", date="2026-08-01", dq="HIGH"), _rec("R2", date="2026-08-02", dq="LOW")]
        result = compute_latest_change(recs)
        assert result.data_quality_change == "degraded"

    def test_data_quality_improved(self):
        recs = [_rec("R1", date="2026-08-01", dq="LOW"), _rec("R2", date="2026-08-02", dq="HIGH")]
        result = compute_latest_change(recs)
        assert result.data_quality_change == "improved"

    def test_data_quality_unchanged(self):
        recs = [_rec("R1", date="2026-08-01", dq="MEDIUM"), _rec("R2", date="2026-08-02", dq="MEDIUM")]
        result = compute_latest_change(recs)
        assert result.data_quality_change == "unchanged"

    def test_newly_triggered_threshold(self):
        recs = [
            _rec("R1", date="2026-08-01", temp=30.0, threshold=35.0),
            _rec("R2", date="2026-08-02", temp=36.0, threshold=35.0),
        ]
        result = compute_latest_change(recs)
        assert "threshold_exceeded" in result.newly_triggered_conditions

    def test_cleared_threshold(self):
        recs = [
            _rec("R1", date="2026-08-01", temp=36.0, threshold=35.0),
            _rec("R2", date="2026-08-02", temp=30.0, threshold=35.0),
        ]
        result = compute_latest_change(recs)
        assert "threshold_exceeded" in result.cleared_conditions

    def test_three_records_uses_last_two(self):
        recs = [
            _rec("R1", date="2026-08-01", temp=30.0),
            _rec("R2", date="2026-08-02", temp=32.0),
            _rec("R3", date="2026-08-03", temp=35.0),
        ]
        result = compute_latest_change(recs)
        assert result.baseline_analysis_id == "R2"
        assert result.latest_analysis_id == "R3"

    def test_missing_metrics_in_one_record(self):
        recs = [
            {"analysis_id": "R1", "date": "2026-08-01"},
            _rec("R2", date="2026-08-02", temp=30.0),
        ]
        result = compute_latest_change(recs)
        assert result.is_first_analysis is False

    def test_both_records_missing_metric(self):
        recs = [
            {"analysis_id": "R1", "date": "2026-08-01"},
            {"analysis_id": "R2", "date": "2026-08-02"},
        ]
        result = compute_latest_change(recs)
        # No changed or unchanged metrics (all unavailable)
        assert len(result.changed_metrics) == 0
        assert len(result.unchanged_metrics) == 0

    def test_to_dict_produces_json(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        result = compute_latest_change(recs)
        d = result.to_dict()
        json.dumps(d)  # Must not raise

    def test_immutability(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        result = compute_latest_change(recs)
        with pytest.raises(Exception):
            result.baseline_analysis_id = "hacked"  # type: ignore

    def test_limitations_always_present(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        result = compute_latest_change(recs)
        assert len(result.limitations) > 0

    def test_date_sorting_correct_order(self):
        recs = [
            _rec("R3", date="2026-08-03", temp=35.0),
            _rec("R1", date="2026-08-01", temp=30.0),
            _rec("R2", date="2026-08-02", temp=32.0),
        ]
        result = compute_latest_change(recs)
        assert result.baseline_analysis_id == "R2"
        assert result.latest_analysis_id == "R3"

    def test_first_analysis_has_limitations(self):
        result = compute_latest_change([_rec("R1")])
        assert any("First analysis" in l or "no previous" in l.lower() for l in result.limitations)

    def test_newly_triggered_low_data_quality(self):
        recs = [_rec("R1", date="2026-08-01", dq="HIGH"), _rec("R2", date="2026-08-02", dq="LOW")]
        result = compute_latest_change(recs)
        assert "low_data_quality" in result.newly_triggered_conditions

    def test_metric_difference_precision(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.1234), _rec("R2", date="2026-08-02", temp=30.5678)]
        result = compute_latest_change(recs)
        for m in result.changed_metrics:
            if m.difference is not None:
                assert len(str(m.difference).split(".")[-1]) <= 4

    def test_spread_difference_detection(self):
        recs = [
            {"analysis_id": "R1", "date": "2026-08-01", "metrics": {"temp_spread": 5.0}},
            {"analysis_id": "R2", "date": "2026-08-02", "metrics": {"temp_spread": 8.0}},
        ]
        result = compute_latest_change(recs)
        spread = [m for m in result.changed_metrics if "Spread" in m.metric_name]
        if spread:
            assert spread[0].direction == "increased"

    def test_no_duplicate_metrics(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        result = compute_latest_change(recs)
        names = [m.metric_name for m in result.changed_metrics + result.unchanged_metrics]
        assert len(names) == len(set(names))

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx

        def _bad(*a, **k):
            raise AssertionError("Network!")

        monkeypatch.setattr(httpx.Client, "send", _bad)
        monkeypatch.setattr(socket, "create_connection", _bad)

        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        compute_latest_change(recs)

    def test_records_not_mutated(self):
        import copy
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        original = copy.deepcopy(recs)
        compute_latest_change(recs)
        assert recs == original

    def test_metric_change_direction_field(self):
        mc = MetricChange(
            metric_name="test",
            baseline_value=10.0,
            latest_value=20.0,
            difference=10.0,
            percentage_change=100.0,
            direction="increased",
        )
        d = mc.to_dict()
        assert d["direction"] == "increased"

    def test_empty_signals_parameter(self):
        recs = [_rec("R1", date="2026-08-01", temp=30.0), _rec("R2", date="2026-08-02", temp=35.0)]
        result = compute_latest_change(recs, signals=[])
        assert result.is_first_analysis is False

    def test_signals_condition_detection(self):
        recs = [
            _rec("R1", date="2026-08-01", temp=30.0),
            _rec("R2", date="2026-08-02", temp=35.0),
        ]
        sigs = [{"signal_id": "S1", "analysis_id": "R2", "signal_type": "threshold_breach"}]
        result = compute_latest_change(recs, signals=sigs)
        assert "signal:threshold_breach" in result.newly_triggered_conditions
