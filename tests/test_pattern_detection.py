"""Test suite for Cross-Analysis Pattern Detection Engine (Phase 17)."""

from __future__ import annotations

import pytest

from frontend.utils.pattern_detection import (
    Pattern,
    detect_all_patterns,
    detect_data_quality_degradation,
    detect_repeated_high_temperature,
    detect_repeated_location_alerts,
    detect_repeated_signal_type,
    detect_repeated_threshold_exceedance,
    detect_recurring_watchlist_matches,
    detect_temperature_direction,
)


def _rec(aid, temp=None, date="2026-08-28", loc="Downtown", dq="HIGH", analysis_type="heatmap"):
    d = {"analysis_id": aid, "date": date, "location_label": loc, "data_quality": dq, "analysis_type": analysis_type}
    if temp is not None:
        d["observed_temperature"] = temp
        d["metrics"] = {"mean_temp": temp}
    return d


class TestRepeatedThresholdExceedance:
    def test_no_records_returns_empty(self):
        assert detect_repeated_threshold_exceedance([]) == []

    def test_single_exceeding_returns_empty(self):
        assert detect_repeated_threshold_exceedance([_rec("R1", 36.0)]) == []

    def test_two_exceeding_returns_pattern(self):
        pats = detect_repeated_threshold_exceedance([_rec("R1", 36.0), _rec("R2", 37.0)])
        assert len(pats) == 1
        assert pats[0].pattern_type == "repeated_threshold_exceedance"
        assert pats[0].count == 2
        assert pats[0].severity == "WATCH"

    def test_three_exceeding_elevates_severity(self):
        pats = detect_repeated_threshold_exceedance([_rec("R1", 36), _rec("R2", 37), _rec("R3", 38)])
        assert pats[0].severity == "ELEVATED"
        assert pats[0].count == 3

    def test_below_threshold_not_counted(self):
        recs = [_rec("R1", 34), _rec("R2", 36), _rec("R3", 37)]
        pats = detect_repeated_threshold_exceedance(recs)
        assert pats[0].count == 2

    def test_custom_threshold(self):
        pats = detect_repeated_threshold_exceedance([_rec("R1", 30), _rec("R2", 31)], threshold=29.0)
        assert len(pats) == 1

    def test_nan_temperature_ignored(self):
        pats = detect_repeated_threshold_exceedance([_rec("R1", float("nan")), _rec("R2", 36)])
        assert pats == []

    def test_none_temperature_ignored(self):
        recs = [_rec("R1", None), _rec("R2", 36)]
        pats = detect_repeated_threshold_exceedance(recs)
        assert pats == []

    def test_pattern_id_is_deterministic(self):
        recs = [_rec("R1", 36), _rec("R2", 37)]
        p1 = detect_repeated_threshold_exceedance(recs)
        p2 = detect_repeated_threshold_exceedance(recs)
        assert p1[0].pattern_id == p2[0].pattern_id

    def test_location_unified_when_same(self):
        recs = [_rec("R1", 36, loc="X"), _rec("R2", 37, loc="X")]
        assert detect_repeated_threshold_exceedance(recs)[0].location == "X"

    def test_location_none_when_different(self):
        recs = [_rec("R1", 36, loc="X"), _rec("R2", 37, loc="Y")]
        assert detect_repeated_threshold_exceedance(recs)[0].location is None


class TestRepeatedHighTemperature:
    def test_no_records_returns_empty(self):
        assert detect_repeated_high_temperature([]) == []

    def test_two_high_temps(self):
        recs = [_rec("R1", 34), _rec("R2", 35)]
        pats = detect_repeated_high_temperature(recs)
        assert len(pats) == 1
        assert "34" in pats[0].evidence[0] or "33" in pats[0].evidence[0]

    def test_custom_high_temp_threshold(self):
        pats = detect_repeated_high_temperature([_rec("R1", 28), _rec("R2", 29)], high_temp_threshold=27.0)
        assert len(pats) == 1

    def test_below_threshold_excluded(self):
        recs = [_rec("R1", 30), _rec("R2", 34)]
        pats = detect_repeated_high_temperature(recs)
        assert pats == []

    def test_explanation_is_descriptive(self):
        recs = [_rec("R1", 34), _rec("R2", 35)]
        pats = detect_repeated_high_temperature(recs)
        assert "caused" not in pats[0].explanation.lower()
        assert "dangerous" not in pats[0].explanation.lower()


class TestRecurringWatchlistMatches:
    def test_no_evaluations(self):
        assert detect_recurring_watchlist_matches([]) == []

    def test_single_match_no_pattern(self):
        evals = [{"watchlist_id": "WL-1", "matched": True, "analysis_id": "R1"}]
        assert detect_recurring_watchlist_matches(evals) == []

    def test_two_matches_same_watchlist(self):
        evals = [
            {"watchlist_id": "WL-1", "matched": True, "analysis_id": "R1"},
            {"watchlist_id": "WL-1", "matched": True, "analysis_id": "R2"},
        ]
        pats = detect_recurring_watchlist_matches(evals)
        assert len(pats) == 1
        assert pats[0].pattern_type == "recurring_watchlist_match"

    def test_unmatched_not_counted(self):
        evals = [
            {"watchlist_id": "WL-1", "matched": True, "analysis_id": "R1"},
            {"watchlist_id": "WL-1", "matched": False, "analysis_id": "R2"},
        ]
        assert detect_recurring_watchlist_matches(evals) == []


class TestRepeatedLocationAlerts:
    def test_no_alerts(self):
        assert detect_repeated_location_alerts([]) == []

    def test_single_location_alert_no_pattern(self):
        alerts = [{"alert_id": "A1", "location_label": "Downtown"}]
        assert detect_repeated_location_alerts(alerts) == []

    def test_two_alerts_same_location(self):
        alerts = [
            {"alert_id": "A1", "location_label": "Downtown"},
            {"alert_id": "A2", "location_label": "Downtown"},
        ]
        pats = detect_repeated_location_alerts(alerts)
        assert len(pats) == 1
        assert pats[0].location == "Downtown"

    def test_different_locations_not_grouped(self):
        alerts = [
            {"alert_id": "A1", "location_label": "North"},
            {"alert_id": "A2", "location_label": "South"},
        ]
        assert detect_repeated_location_alerts(alerts) == []

    def test_three_alerts_elevated_severity(self):
        alerts = [
            {"alert_id": f"A{i}", "location_label": "X"} for i in range(3)
        ]
        pats = detect_repeated_location_alerts(alerts)
        assert pats[0].severity == "ELEVATED"


class TestRepeatedSignalType:
    def test_no_signals(self):
        assert detect_repeated_signal_type([]) == []

    def test_two_same_type(self):
        sigs = [
            {"signal_id": "S1", "signal_type": "threshold_breach", "analysis_id": "R1"},
            {"signal_id": "S2", "signal_type": "threshold_breach", "analysis_id": "R2"},
        ]
        pats = detect_repeated_signal_type(sigs)
        assert len(pats) == 1
        assert pats[0].count == 2

    def test_different_types_not_grouped(self):
        sigs = [
            {"signal_id": "S1", "signal_type": "threshold_breach"},
            {"signal_id": "S2", "signal_type": "data_quality"},
        ]
        assert detect_repeated_signal_type(sigs) == []


class TestDataQualityDegradation:
    def test_no_records(self):
        assert detect_data_quality_degradation([]) == []

    def test_single_record(self):
        assert detect_data_quality_degradation([_rec("R1")]) == []

    def test_degradation_detected(self):
        recs = [
            _rec("R1", dq="HIGH", date="2026-08-01"),
            _rec("R2", dq="LOW", date="2026-08-02"),
        ]
        pats = detect_data_quality_degradation(recs)
        assert len(pats) == 1
        assert pats[0].pattern_type == "data_quality_degradation"

    def test_improvement_not_flagged(self):
        recs = [
            _rec("R1", dq="LOW", date="2026-08-01"),
            _rec("R2", dq="HIGH", date="2026-08-02"),
        ]
        assert detect_data_quality_degradation(recs) == []

    def test_stable_quality_not_flagged(self):
        recs = [_rec(f"R{i}", dq="HIGH", date=f"2026-08-{i+1:02d}") for i in range(5)]
        assert detect_data_quality_degradation(recs) == []


class TestTemperatureDirection:
    def test_no_records(self):
        assert detect_temperature_direction([]) == []

    def test_two_records_not_enough(self):
        assert detect_temperature_direction([_rec("R1", 30), _rec("R2", 31)]) == []

    def test_three_increasing_detected(self):
        recs = [
            _rec("R1", 30, date="2026-08-01"),
            _rec("R2", 31, date="2026-08-02"),
            _rec("R3", 32, date="2026-08-03"),
        ]
        pats = detect_temperature_direction(recs)
        assert len(pats) == 1
        assert "increased" in pats[0].explanation

    def test_three_decreasing_detected(self):
        recs = [
            _rec("R1", 35, date="2026-08-01"),
            _rec("R2", 33, date="2026-08-02"),
            _rec("R3", 31, date="2026-08-03"),
        ]
        pats = detect_temperature_direction(recs)
        assert "decreased" in pats[0].explanation

    def test_mixed_direction_no_pattern(self):
        recs = [
            _rec("R1", 30, date="2026-08-01"),
            _rec("R2", 32, date="2026-08-02"),
            _rec("R3", 29, date="2026-08-03"),
        ]
        assert detect_temperature_direction(recs) == []

    def test_no_causal_language(self):
        recs = [_rec(f"R{i}", 30 + i, date=f"2026-08-{i+1:02d}") for i in range(4)]
        pats = detect_temperature_direction(recs)
        for p in pats:
            assert "caused" not in p.explanation.lower()
            assert "dangerous" not in p.explanation.lower()
            assert "worsening" not in p.explanation.lower()

    def test_flat_temperature_is_increasing(self):
        recs = [_rec(f"R{i}", 30, date=f"2026-08-{i+1:02d}") for i in range(3)]
        pats = detect_temperature_direction(recs)
        # Flat is both increasing and decreasing (<=), so should detect
        assert len(pats) >= 1


class TestDetectAllPatterns:
    def test_empty_inputs(self):
        assert detect_all_patterns() == []

    def test_combined_detection(self):
        recs = [
            _rec("R1", 36, date="2026-08-01", dq="HIGH"),
            _rec("R2", 37, date="2026-08-02", dq="LOW"),
            _rec("R3", 38, date="2026-08-03", dq="LOW"),
        ]
        pats = detect_all_patterns(records=recs)
        types = {p.pattern_type for p in pats}
        assert "repeated_threshold_exceedance" in types
        assert "repeated_high_temperature" in types

    def test_pattern_immutability(self):
        recs = [_rec("R1", 36), _rec("R2", 37)]
        pats = detect_repeated_threshold_exceedance(recs)
        with pytest.raises(Exception):
            pats[0].count = 99  # type: ignore

    def test_limitations_always_present(self):
        recs = [_rec("R1", 36), _rec("R2", 37)]
        pats = detect_repeated_threshold_exceedance(recs)
        assert len(pats[0].limitations) > 0

    def test_to_dict_produces_json_serializable(self):
        import json
        recs = [_rec("R1", 36), _rec("R2", 37)]
        pats = detect_repeated_threshold_exceedance(recs)
        json.dumps(pats[0].to_dict())  # Should not raise
