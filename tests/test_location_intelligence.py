"""Test suite for Location-Centric Intelligence Engine (Phase 17)."""

from __future__ import annotations

import json
import pytest

from frontend.utils.location_intelligence import (
    LocationSummary,
    build_location_summaries,
)


def _rec(aid, loc="Downtown", temp=None, date="2026-08-28", dq="HIGH"):
    d = {"analysis_id": aid, "location_label": loc, "date": date, "data_quality": dq}
    if temp is not None:
        d["observed_temperature"] = temp
        d["metrics"] = {"mean_temp": temp}
    return d


class TestLocationSummaries:
    def test_empty_records(self):
        result = build_location_summaries([])
        assert result == []

    def test_single_location_single_record(self):
        result = build_location_summaries([_rec("R1", "North", 32.5)])
        assert len(result) == 1
        assert result[0].location == "North"
        assert result[0].total_analyses == 1
        assert result[0].latest_observation == 32.5
        assert result[0].previous_observation is None
        assert result[0].temperature_change is None

    def test_single_location_two_records(self):
        recs = [_rec("R1", "North", 30.0, "2026-08-01"), _rec("R2", "North", 33.0, "2026-08-02")]
        result = build_location_summaries(recs)
        assert result[0].total_analyses == 2
        assert result[0].latest_observation == 33.0
        assert result[0].previous_observation == 30.0
        assert result[0].temperature_change == 3.0

    def test_two_locations_grouped_separately(self):
        recs = [_rec("R1", "North", 30.0), _rec("R2", "South", 32.0)]
        result = build_location_summaries(recs)
        assert len(result) == 2
        locs = {r.location for r in result}
        assert locs == {"North", "South"}

    def test_location_sorting_alphabetical(self):
        recs = [_rec("R1", "Zulu"), _rec("R2", "Alpha"), _rec("R3", "Middle")]
        result = build_location_summaries(recs)
        assert [r.location for r in result] == ["Alpha", "Middle", "Zulu"]

    def test_records_without_location_excluded(self):
        recs = [{"analysis_id": "R1"}, _rec("R2", "Downtown", 30.0)]
        result = build_location_summaries(recs)
        assert len(result) == 1
        assert result[0].location == "Downtown"

    def test_whitespace_location_excluded(self):
        recs = [{"analysis_id": "R1", "location_label": "   "}, _rec("R2", "X", 30.0)]
        result = build_location_summaries(recs)
        assert len(result) == 1

    def test_date_range_per_location(self):
        recs = [
            _rec("R1", "North", 30.0, "2026-08-01"),
            _rec("R2", "North", 33.0, "2026-08-15"),
            _rec("R3", "North", 32.0, "2026-08-10"),
        ]
        result = build_location_summaries(recs)
        assert result[0].earliest_date == "2026-08-01"
        assert result[0].latest_date == "2026-08-15"

    def test_active_alerts_counted(self):
        recs = [_rec("R1", "Downtown", 30.0)]
        alerts = [
            {"alert_id": "A1", "location_label": "Downtown", "status": "ACTIVE"},
            {"alert_id": "A2", "location_label": "Downtown", "status": "RESOLVED"},
        ]
        result = build_location_summaries(recs, alerts=alerts)
        assert result[0].active_alerts == 1

    def test_open_investigations_counted(self):
        recs = [_rec("R1", "Downtown", 30.0)]
        queue = [{"queue_id": "Q1", "analysis_id": "R1", "status": "OPEN"}]
        result = build_location_summaries(recs, queue_items=queue)
        assert result[0].open_investigations == 1

    def test_watchlists_matched_counted(self):
        recs = [_rec("R1", "Downtown", 30.0)]
        wl_evals = [{"watchlist_id": "WL-1", "analysis_id": "R1", "matched": True}]
        result = build_location_summaries(recs, watchlist_evaluations=wl_evals)
        assert result[0].watchlists_matched == 1

    def test_data_quality_worst_of_group(self):
        recs = [
            _rec("R1", "North", 30.0, dq="HIGH"),
            _rec("R2", "North", 32.0, dq="LOW"),
        ]
        result = build_location_summaries(recs)
        assert result[0].data_quality == "LOW"

    def test_analysis_ids_listed(self):
        recs = [_rec("R1", "North"), _rec("R2", "North")]
        result = build_location_summaries(recs)
        assert "R1" in result[0].analysis_ids
        assert "R2" in result[0].analysis_ids

    def test_to_dict_json_serializable(self):
        recs = [_rec("R1", "North", 30.0)]
        result = build_location_summaries(recs)
        json.dumps(result[0].to_dict())

    def test_immutability(self):
        recs = [_rec("R1", "North", 30.0)]
        result = build_location_summaries(recs)
        with pytest.raises(Exception):
            result[0].total_analyses = 99  # type: ignore

    def test_limitations_present(self):
        recs = [_rec("R1", "North")]
        result = build_location_summaries(recs)
        assert len(result[0].limitations) > 0

    def test_limited_data_limitation(self):
        recs = [_rec("R1", "North")]
        result = build_location_summaries(recs)
        assert any("Limited" in l or "more data" in l.lower() for l in result[0].limitations)

    def test_temperature_change_negative(self):
        recs = [_rec("R1", "N", 35.0, "2026-08-01"), _rec("R2", "N", 30.0, "2026-08-02")]
        result = build_location_summaries(recs)
        assert result[0].temperature_change == -5.0

    def test_missing_temperature_no_change(self):
        recs = [_rec("R1", "N"), _rec("R2", "N")]
        result = build_location_summaries(recs)
        assert result[0].temperature_change is None

    def test_many_locations(self):
        recs = [_rec(f"R{i}", f"Loc-{i}", 30.0 + i) for i in range(10)]
        result = build_location_summaries(recs)
        assert len(result) == 10

    def test_suppressed_alerts_excluded(self):
        recs = [_rec("R1", "Downtown")]
        alerts = [{"alert_id": "A1", "location_label": "Downtown", "status": "SUPPRESSED"}]
        result = build_location_summaries(recs, alerts=alerts)
        assert result[0].active_alerts == 0

    def test_resolved_investigations_not_counted(self):
        recs = [_rec("R1", "Downtown")]
        queue = [{"queue_id": "Q1", "analysis_id": "R1", "status": "RESOLVED"}]
        result = build_location_summaries(recs, queue_items=queue)
        assert result[0].open_investigations == 0

    def test_unmatched_watchlist_not_counted(self):
        recs = [_rec("R1", "Downtown")]
        wl_evals = [{"watchlist_id": "WL-1", "analysis_id": "R1", "matched": False}]
        result = build_location_summaries(recs, watchlist_evaluations=wl_evals)
        assert result[0].watchlists_matched == 0

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx
        def _bad(*a, **k):
            raise AssertionError("Network!")
        monkeypatch.setattr(httpx.Client, "send", _bad)
        monkeypatch.setattr(socket, "create_connection", _bad)
        recs = [_rec("R1", "Downtown", 30.0)]
        build_location_summaries(recs)

    def test_records_not_mutated(self):
        import copy
        recs = [_rec("R1", "Downtown", 30.0)]
        orig = copy.deepcopy(recs)
        build_location_summaries(recs)
        assert recs == orig

    def test_investigation_linked_by_location_on_queue_item(self):
        recs = [_rec("R1", "Downtown")]
        queue = [{"queue_id": "Q1", "location_label": "Downtown", "status": "OPEN"}]
        result = build_location_summaries(recs, queue_items=queue)
        assert result[0].open_investigations == 1

    def test_three_or_more_records_drops_limited_data_limitation(self):
        recs = [_rec(f"R{i}", "North", 30.0 + i, f"2026-08-{i+1:02d}") for i in range(3)]
        result = build_location_summaries(recs)
        assert not any("Limited" in l for l in result[0].limitations)

    def test_location_label_trimmed(self):
        recs = [_rec("R1", "  Downtown  ", 30.0)]
        result = build_location_summaries(recs)
        assert result[0].location == "Downtown"

    def test_four_records_temperature_change_uses_last_two(self):
        recs = [
            _rec("R1", "N", 28.0, "2026-08-01"),
            _rec("R2", "N", 30.0, "2026-08-02"),
            _rec("R3", "N", 32.0, "2026-08-03"),
            _rec("R4", "N", 35.0, "2026-08-04"),
        ]
        result = build_location_summaries(recs)
        assert result[0].latest_observation == 35.0
        assert result[0].previous_observation == 32.0
        assert result[0].temperature_change == 3.0
