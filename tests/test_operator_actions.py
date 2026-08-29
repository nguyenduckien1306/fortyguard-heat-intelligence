"""Test suite for Operator Action Recommendations Engine (Phase 17)."""

from __future__ import annotations

import json
import pytest

from frontend.utils.operator_actions import (
    ActionRecommendation,
    generate_alert_actions,
    generate_all_actions,
    generate_comparison_actions,
    generate_investigation_actions,
    generate_watchlist_actions,
)


def _alert(aid, severity="CRITICAL", status="ACTIVE", evidence=None):
    d = {"alert_id": aid, "severity": severity, "status": status}
    if evidence:
        d["evidence"] = evidence
    return d


def _queue(qid, status="OPEN"):
    return {"queue_id": qid, "status": status}


def _rec(aid, date="2026-08-28"):
    return {"analysis_id": aid, "date": date}


def _wl_eval(wlid, matched=True):
    return {"watchlist_id": wlid, "matched": matched}


class TestOperatorActions:
    def test_alert_without_evidence_generates_investigate_action(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        actions = generate_alert_actions(alerts)
        assert len(actions) == 1
        assert actions[0].source_object_id == "A1"
        assert actions[0].source_object_type == "alert"
        assert "Investigate" in actions[0].title
        assert actions[0].destination_ui_state == "investigation_queue"

    def test_alert_with_evidence_generates_review_evidence_action(self):
        alerts = [_alert("A1", severity="ELEVATED", evidence={"bundle": "123"})]
        actions = generate_alert_actions(alerts)
        assert len(actions) == 1
        assert "Review evidence" in actions[0].title
        assert actions[0].destination_ui_state == "alert_detail"

    def test_resolved_alert_generates_no_action(self):
        alerts = [_alert("A1", status="RESOLVED")]
        actions = generate_alert_actions(alerts)
        assert actions == []

    def test_dismissed_alert_generates_no_action(self):
        alerts = [_alert("A1", status="DISMISSED")]
        actions = generate_alert_actions(alerts)
        assert actions == []

    def test_open_investigation_generates_begin_review_action(self):
        q = [_queue("Q1", status="OPEN")]
        actions = generate_investigation_actions(q)
        assert len(actions) == 1
        assert "Begin review" in actions[0].title
        assert actions[0].source_object_type == "investigation"
        assert actions[0].destination_ui_state == "investigation_detail"

    def test_in_review_investigation_generates_complete_review_action(self):
        q = [_queue("Q1", status="IN_REVIEW")]
        actions = generate_investigation_actions(q)
        assert len(actions) == 1
        assert "Complete review" in actions[0].title

    def test_resolved_investigation_generates_no_action(self):
        q = [_queue("Q1", status="RESOLVED")]
        actions = generate_investigation_actions(q)
        assert actions == []

    def test_single_record_generates_no_comparison_action(self):
        recs = [_rec("R1")]
        actions = generate_comparison_actions(recs)
        assert actions == []

    def test_two_records_generate_comparison_action(self):
        recs = [_rec("R1", date="2026-08-01"), _rec("R2", date="2026-08-02")]
        actions = generate_comparison_actions(recs)
        assert len(actions) == 1
        assert "Compare analysis R2 with previous R1" in actions[0].title
        assert actions[0].destination_ui_state == "change_detection"

    def test_matched_watchlist_generates_review_action(self):
        evals = [_wl_eval("WL-1", matched=True)]
        actions = generate_watchlist_actions(evals)
        assert len(actions) == 1
        assert "Review triggered watchlist WL-1" in actions[0].title
        assert actions[0].destination_ui_state == "watchlist_detail"

    def test_unmatched_watchlist_generates_no_action(self):
        evals = [_wl_eval("WL-1", matched=False)]
        actions = generate_watchlist_actions(evals)
        assert actions == []

    def test_generate_all_actions_combines_and_sorts_by_priority(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        q = [_queue("Q1", status="OPEN")]
        recs = [_rec("R1", date="2026-08-01"), _rec("R2", date="2026-08-02")]
        evals = [_wl_eval("WL-1", matched=True)]

        actions = generate_all_actions(
            alerts=alerts,
            queue_items=q,
            records=recs,
            watchlist_evaluations=evals,
        )

        assert len(actions) == 4
        # Sorted descending by priority
        for i in range(len(actions) - 1):
            assert actions[i].priority >= actions[i + 1].priority

    def test_critical_alert_has_higher_priority_than_comparison(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        recs = [_rec("R1", "2026-08-01"), _rec("R2", "2026-08-02")]
        actions = generate_all_actions(alerts=alerts, records=recs)
        assert actions[0].source_object_type == "alert"

    def test_no_medical_safety_evacuation_language_in_actions(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        actions = generate_all_actions(alerts=alerts)
        for act in actions:
            text = f"{act.title} {act.reason}".lower()
            assert "evacuate" not in text
            assert "medical" not in text
            assert "dangerous" not in text
            assert "fatal" not in text
            assert "health risk" not in text

    def test_action_id_is_deterministic(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        a1 = generate_alert_actions(alerts)
        a2 = generate_alert_actions(alerts)
        assert a1[0].action_id == a2[0].action_id

    def test_to_dict_json_serializable(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        actions = generate_alert_actions(alerts)
        d = actions[0].to_dict()
        assert isinstance(d, dict)
        json.dumps(d)

    def test_immutability(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        actions = generate_alert_actions(alerts)
        with pytest.raises(Exception):
            actions[0].priority = 999.0  # type: ignore

    def test_empty_inputs_returns_empty_list(self):
        assert generate_all_actions() == []

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx

        def _bad(*a, **k):
            raise AssertionError("Network!")

        monkeypatch.setattr(httpx.Client, "send", _bad)
        monkeypatch.setattr(socket, "create_connection", _bad)

        generate_all_actions(alerts=[_alert("A1")])

    def test_inputs_not_mutated(self):
        import copy
        alerts = [_alert("A1", severity="CRITICAL")]
        orig = copy.deepcopy(alerts)
        generate_all_actions(alerts=alerts)
        assert alerts == orig

    def test_info_alert_has_lower_priority_than_critical(self):
        a_crit = _alert("A1", severity="CRITICAL")
        a_info = _alert("A2", severity="INFO")
        actions = generate_all_actions(alerts=[a_crit, a_info])
        assert actions[0].source_object_id == "A1"
        assert actions[1].source_object_id == "A2"

    def test_status_triggered_on_watchlist_eval_generates_action(self):
        evals = [{"watchlist_id": "WL-2", "status": "TRIGGERED"}]
        actions = generate_watchlist_actions(evals)
        assert len(actions) == 1

    def test_object_with_to_dict_supported(self):
        class Obj:
            def to_dict(self):
                return {"alert_id": "OBJ-1", "severity": "WATCH", "status": "ACTIVE"}
        actions = generate_alert_actions([Obj()])
        assert len(actions) == 1
        assert actions[0].source_object_id == "OBJ-1"

    def test_three_records_comparison_uses_last_two(self):
        recs = [
            _rec("R1", date="2026-08-01"),
            _rec("R2", date="2026-08-02"),
            _rec("R3", date="2026-08-03"),
        ]
        actions = generate_comparison_actions(recs)
        assert len(actions) == 1
        assert "R3" in actions[0].title
        assert "R2" in actions[0].title

    def test_all_actions_have_valid_destination_ui_state(self):
        alerts = [_alert("A1", severity="CRITICAL")]
        q = [_queue("Q1", status="OPEN")]
        recs = [_rec("R1", date="2026-08-01"), _rec("R2", date="2026-08-02")]
        evals = [_wl_eval("WL-1", matched=True)]
        actions = generate_all_actions(alerts=alerts, queue_items=q, records=recs, watchlist_evaluations=evals)
        for act in actions:
            assert act.destination_ui_state in (
                "alert_detail",
                "investigation_queue",
                "investigation_detail",
                "change_detection",
                "watchlist_detail",
            )
