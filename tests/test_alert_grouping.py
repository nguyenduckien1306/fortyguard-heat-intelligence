"""Test suite for Alert Clustering / Related Alerts Engine (Phase 17)."""

from __future__ import annotations

import json
import pytest

from frontend.utils.alert_grouping import (
    AlertGroup,
    group_alerts,
)


def _alert(aid, analysis_id="R1", loc=None, watchlist_id=None, signal_type=None,
           criterion=None, severity="WATCH", status="ACTIVE", evidence=None):
    d = {"alert_id": aid, "analysis_id": analysis_id, "severity": severity, "status": status}
    if loc:
        d["location_label"] = loc
    if watchlist_id:
        d["watchlist_id"] = watchlist_id
    if signal_type:
        d["signal_type"] = signal_type
    if criterion:
        d["criterion"] = criterion
    if evidence:
        d["evidence"] = evidence
    return d


class TestAlertGrouping:
    def test_empty_alerts(self):
        assert group_alerts([]) == []

    def test_single_alert_no_groups(self):
        assert group_alerts([_alert("A1")]) == []

    def test_two_alerts_same_analysis_grouped(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        result = group_alerts(alerts)
        assert len(result) >= 1
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert len(analysis_groups) == 1
        assert set(analysis_groups[0].member_alert_ids) == {"A1", "A2"}

    def test_two_alerts_same_location_grouped(self):
        alerts = [
            _alert("A1", analysis_id="R1", loc="Downtown"),
            _alert("A2", analysis_id="R2", loc="Downtown"),
        ]
        result = group_alerts(alerts)
        loc_groups = [g for g in result if g.grouping_key == "location"]
        assert len(loc_groups) == 1
        assert loc_groups[0].grouping_value == "Downtown"

    def test_different_locations_not_grouped(self):
        alerts = [
            _alert("A1", loc="North"),
            _alert("A2", loc="South"),
        ]
        result = group_alerts(alerts)
        loc_groups = [g for g in result if g.grouping_key == "location"]
        assert len(loc_groups) == 0

    def test_same_watchlist_grouped(self):
        alerts = [
            _alert("A1", watchlist_id="WL-1"),
            _alert("A2", watchlist_id="WL-1"),
        ]
        result = group_alerts(alerts)
        wl_groups = [g for g in result if g.grouping_key == "watchlist_id"]
        assert len(wl_groups) == 1

    def test_same_signal_type_grouped(self):
        alerts = [
            _alert("A1", signal_type="threshold_breach"),
            _alert("A2", signal_type="threshold_breach"),
        ]
        result = group_alerts(alerts)
        sig_groups = [g for g in result if g.grouping_key == "signal_type"]
        assert len(sig_groups) == 1

    def test_same_criterion_grouped(self):
        alerts = [
            _alert("A1", criterion="temp_watch"),
            _alert("A2", criterion="temp_watch"),
        ]
        result = group_alerts(alerts)
        crit_groups = [g for g in result if g.grouping_key == "criterion"]
        assert len(crit_groups) == 1

    def test_dominant_severity_is_highest(self):
        alerts = [
            _alert("A1", severity="CRITICAL"),
            _alert("A2", severity="WATCH"),
        ]
        result = group_alerts(alerts)
        for g in result:
            assert g.dominant_severity == "CRITICAL"

    def test_group_sorted_by_severity(self):
        alerts = [
            _alert("A1", analysis_id="R1", severity="WATCH"),
            _alert("A2", analysis_id="R1", severity="WATCH"),
            _alert("A3", analysis_id="R2", loc="X", severity="CRITICAL"),
            _alert("A4", analysis_id="R2", loc="X", severity="CRITICAL"),
        ]
        result = group_alerts(alerts)
        if len(result) >= 2:
            assert result[0].dominant_severity == "CRITICAL"

    def test_group_id_is_deterministic(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        r1 = group_alerts(alerts)
        r2 = group_alerts(alerts)
        ids1 = {g.group_id for g in r1}
        ids2 = {g.group_id for g in r2}
        assert ids1 == ids2

    def test_group_title_present(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        result = group_alerts(alerts)
        for g in result:
            assert len(g.group_title) > 0

    def test_evidence_count(self):
        alerts = [
            _alert("A1", analysis_id="R1", evidence={"key": "value"}),
            _alert("A2", analysis_id="R1"),
        ]
        result = group_alerts(alerts)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].evidence_count == 1

    def test_investigation_state_open(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        queue = [{"queue_id": "Q1", "analysis_id": "R1", "status": "OPEN"}]
        result = group_alerts(alerts, queue_items=queue)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].investigation_state == "open"

    def test_investigation_state_resolved(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        queue = [{"queue_id": "Q1", "analysis_id": "R1", "status": "RESOLVED"}]
        result = group_alerts(alerts, queue_items=queue)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].investigation_state == "resolved"

    def test_investigation_state_none_when_no_queue(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        result = group_alerts(alerts)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].investigation_state == "none"

    def test_to_dict_json_serializable(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        result = group_alerts(alerts)
        for g in result:
            json.dumps(g.to_dict())

    def test_immutability(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        result = group_alerts(alerts)
        with pytest.raises(Exception):
            result[0].group_title = "hacked"  # type: ignore

    def test_highest_priority_numeric(self):
        alerts = [
            {"alert_id": "A1", "analysis_id": "R1", "priority_score": 75.0, "severity": "WATCH"},
            {"alert_id": "A2", "analysis_id": "R1", "priority_score": 90.0, "severity": "CRITICAL"},
        ]
        result = group_alerts(alerts)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].highest_priority == 90.0

    def test_member_alert_ids_sorted(self):
        alerts = [_alert("A3", analysis_id="R1"), _alert("A1", analysis_id="R1")]
        result = group_alerts(alerts)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].member_alert_ids == ["A1", "A3"]

    def test_multiple_grouping_keys_for_same_alerts(self):
        alerts = [
            _alert("A1", analysis_id="R1", loc="Downtown"),
            _alert("A2", analysis_id="R1", loc="Downtown"),
        ]
        result = group_alerts(alerts)
        keys = {g.grouping_key for g in result}
        assert "analysis_id" in keys
        assert "location" in keys

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx
        def _bad(*a, **k):
            raise AssertionError("Network!")
        monkeypatch.setattr(httpx.Client, "send", _bad)
        monkeypatch.setattr(socket, "create_connection", _bad)
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        group_alerts(alerts)

    def test_none_inputs(self):
        assert group_alerts(None) == []

    def test_in_review_investigation_state(self):
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        queue = [{"queue_id": "Q1", "analysis_id": "R1", "status": "IN_REVIEW"}]
        result = group_alerts(alerts, queue_items=queue)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert analysis_groups[0].investigation_state == "in_review"

    def test_three_alerts_all_grouped(self):
        alerts = [_alert(f"A{i}", analysis_id="R1") for i in range(3)]
        result = group_alerts(alerts)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id"]
        assert len(analysis_groups[0].member_alert_ids) == 3

    def test_mixed_locations_and_analyses(self):
        alerts = [
            _alert("A1", analysis_id="R1", loc="North"),
            _alert("A2", analysis_id="R1", loc="South"),
            _alert("A3", analysis_id="R2", loc="North"),
        ]
        result = group_alerts(alerts)
        analysis_groups = [g for g in result if g.grouping_key == "analysis_id" and g.grouping_value == "R1"]
        loc_groups = [g for g in result if g.grouping_key == "location" and g.grouping_value == "North"]
        assert len(analysis_groups) == 1
        assert len(loc_groups) == 1

    def test_no_false_grouping_of_different_criteria(self):
        alerts = [
            _alert("A1", criterion="temp_watch"),
            _alert("A2", criterion="humidity_watch"),
        ]
        result = group_alerts(alerts)
        crit_groups = [g for g in result if g.grouping_key == "criterion"]
        assert len(crit_groups) == 0

    def test_group_alerts_preserves_input_integrity(self):
        import copy
        alerts = [_alert("A1", analysis_id="R1"), _alert("A2", analysis_id="R1")]
        orig = copy.deepcopy(alerts)
        group_alerts(alerts)
        assert alerts == orig

    def test_group_alerts_object_with_to_dict(self):
        class AlertObj:
            def __init__(self, aid, analysis_id):
                self.aid = aid
                self.analysis_id = analysis_id
            def to_dict(self):
                return {"alert_id": self.aid, "analysis_id": self.analysis_id, "severity": "WATCH"}

        objs = [AlertObj("A1", "R1"), AlertObj("A2", "R1")]
        result = group_alerts(objs)
        assert len(result) >= 1
        assert "A1" in result[0].member_alert_ids

    def test_grouping_ignores_empty_string_location(self):
        alerts = [_alert("A1", loc="   "), _alert("A2", loc="   ")]
        result = group_alerts(alerts)
        loc_groups = [g for g in result if g.grouping_key == "location"]
        assert len(loc_groups) == 0

    def test_grouping_with_large_number_of_alerts(self):
        alerts = [_alert(f"A{i}", analysis_id=f"R{i%3}", loc=f"Loc{i%2}") for i in range(30)]
        result = group_alerts(alerts)
        assert len(result) > 0

