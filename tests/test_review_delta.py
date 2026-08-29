"""Test suite for Session-Local Review Delta Engine (Phase 17)."""

from __future__ import annotations

import json
import pytest

from frontend.utils.clock import FrozenClock
from frontend.utils.review_delta import (
    ReviewDelta,
    compute_review_delta,
)


def _rec(aid, created_at="2026-08-28T12:00:00Z"):
    return {"analysis_id": aid, "created_at": created_at}


def _sig(sid, created_at="2026-08-28T12:00:00Z"):
    return {"signal_id": sid, "created_at": created_at}


def _alert(aid, created_at="2026-08-28T12:00:00Z", status="ACTIVE"):
    return {"alert_id": aid, "created_at": created_at, "status": status}


def _queue(qid, created_at="2026-08-28T12:00:00Z", status="OPEN"):
    return {"queue_id": qid, "created_at": created_at, "status": status}


class TestReviewDelta:
    def test_no_previous_review_marks_all_items_as_new(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        recs = [_rec("R1"), _rec("R2")]
        sigs = [_sig("S1")]
        alerts = [_alert("A1")]
        q = [_queue("Q1")]

        delta = compute_review_delta(
            last_review_timestamp=None,
            records=recs,
            signals=sigs,
            alerts=alerts,
            queue_items=q,
            clock=clk,
        )

        assert delta.last_review_timestamp is None
        assert delta.has_changes is True
        assert delta.new_analyses == ["R1", "R2"]
        assert delta.new_signals == ["S1"]
        assert delta.new_alerts == ["A1"]
        assert delta.new_investigations == ["Q1"]

    def test_no_changes_when_marker_is_after_all_items(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T14:00:00Z"
        recs = [_rec("R1", created_at="2026-08-28T10:00:00Z")]
        sigs = [_sig("S1", created_at="2026-08-28T11:00:00Z")]
        alerts = [_alert("A1", created_at="2026-08-28T12:00:00Z")]

        delta = compute_review_delta(
            last_review_timestamp=marker,
            records=recs,
            signals=sigs,
            alerts=alerts,
            clock=clk,
        )

        assert delta.has_changes is False
        assert delta.new_analyses == []
        assert delta.new_signals == []
        assert delta.new_alerts == []

    def test_new_analysis_after_marker(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        recs = [
            _rec("R1", created_at="2026-08-28T11:00:00Z"),
            _rec("R2", created_at="2026-08-28T13:00:00Z"),
        ]
        delta = compute_review_delta(last_review_timestamp=marker, records=recs, clock=clk)
        assert delta.has_changes is True
        assert delta.new_analyses == ["R2"]

    def test_new_signals_after_marker(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        sigs = [
            _sig("S1", created_at="2026-08-28T10:00:00Z"),
            _sig("S2", created_at="2026-08-28T14:00:00Z"),
        ]
        delta = compute_review_delta(last_review_timestamp=marker, signals=sigs, clock=clk)
        assert delta.new_signals == ["S2"]

    def test_new_alerts_after_marker(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        alerts = [
            _alert("A1", created_at="2026-08-28T11:00:00Z"),
            _alert("A2", created_at="2026-08-28T13:00:00Z"),
        ]
        delta = compute_review_delta(last_review_timestamp=marker, alerts=alerts, clock=clk)
        assert delta.new_alerts == ["A2"]

    def test_alerts_changed_state_detected(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        alerts = [_alert("A1", created_at="2026-08-28T10:00:00Z", status="RESOLVED")]
        prev_states = {"A1": "ACTIVE"}

        delta = compute_review_delta(
            last_review_timestamp=marker,
            alerts=alerts,
            previous_alert_states=prev_states,
            clock=clk,
        )

        assert delta.has_changes is True
        assert len(delta.alerts_changed_state) == 1
        assert delta.alerts_changed_state[0] == {"alert_id": "A1", "old": "ACTIVE", "new": "RESOLVED"}

    def test_alerts_unchanged_state_not_reported(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        alerts = [_alert("A1", created_at="2026-08-28T10:00:00Z", status="ACTIVE")]
        prev_states = {"A1": "ACTIVE"}

        delta = compute_review_delta(
            last_review_timestamp=marker,
            alerts=alerts,
            previous_alert_states=prev_states,
            clock=clk,
        )

        assert len(delta.alerts_changed_state) == 0

    def test_new_investigation_after_marker(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        q = [_queue("Q1", created_at="2026-08-28T14:00:00Z")]
        delta = compute_review_delta(last_review_timestamp=marker, queue_items=q, clock=clk)
        assert delta.new_investigations == ["Q1"]

    def test_investigation_resolved_since_marker(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        q = [_queue("Q1", created_at="2026-08-28T10:00:00Z", status="RESOLVED")]
        prev_q = {"Q1": "OPEN"}

        delta = compute_review_delta(
            last_review_timestamp=marker,
            queue_items=q,
            previous_queue_states=prev_q,
            clock=clk,
        )

        assert delta.has_changes is True
        assert delta.investigations_resolved == ["Q1"]

    def test_watchlists_newly_triggered_after_marker(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        wl_evals = [
            {"watchlist_id": "WL-1", "matched": True, "created_at": "2026-08-28T14:00:00Z"},
            {"watchlist_id": "WL-2", "matched": True, "created_at": "2026-08-28T10:00:00Z"},
        ]
        delta = compute_review_delta(
            last_review_timestamp=marker,
            watchlist_evaluations=wl_evals,
            clock=clk,
        )
        assert delta.watchlists_newly_triggered == ["WL-1"]

    def test_unmatched_watchlists_ignored(self):
        clk = FrozenClock(frozen_time="2026-08-28T15:00:00Z")
        marker = "2026-08-28T12:00:00Z"
        wl_evals = [{"watchlist_id": "WL-1", "matched": False, "created_at": "2026-08-28T14:00:00Z"}]
        delta = compute_review_delta(last_review_timestamp=marker, watchlist_evaluations=wl_evals, clock=clk)
        assert delta.watchlists_newly_triggered == []

    def test_deterministic_current_timestamp_from_clock(self):
        clk = FrozenClock(frozen_time="2026-08-28T18:30:00Z")
        delta = compute_review_delta(last_review_timestamp="2026-08-28T12:00:00Z", clock=clk)
        assert "2026-08-28T18:30:00" in delta.current_timestamp

    def test_to_dict_json_serializable(self):
        clk = FrozenClock(frozen_time="2026-08-28T18:30:00Z")
        delta = compute_review_delta(last_review_timestamp=None, records=[_rec("R1")], clock=clk)
        d = delta.to_dict()
        assert isinstance(d, dict)
        json.dumps(d)

    def test_immutability(self):
        delta = compute_review_delta(last_review_timestamp=None)
        with pytest.raises(Exception):
            delta.has_changes = False  # type: ignore

    def test_all_empty_inputs(self):
        delta = compute_review_delta(last_review_timestamp="2026-08-28T12:00:00Z")
        assert delta.has_changes is False
        assert delta.new_analyses == []

    def test_item_missing_timestamp_not_reported_as_new(self):
        marker = "2026-08-28T12:00:00Z"
        recs = [{"analysis_id": "R1"}]  # no timestamp
        delta = compute_review_delta(last_review_timestamp=marker, records=recs)
        assert "R1" not in delta.new_analyses

    def test_item_date_field_fallback(self):
        marker = "2026-08-28T10:00:00Z"
        recs = [{"analysis_id": "R1", "date": "2026-08-29"}]
        delta = compute_review_delta(last_review_timestamp=marker, records=recs)
        assert "R1" in delta.new_analyses

    def test_timezone_naive_marker_and_aware_item(self):
        marker = "2026-08-28T12:00:00"
        recs = [_rec("R1", created_at="2026-08-28T14:00:00+00:00")]
        delta = compute_review_delta(last_review_timestamp=marker, records=recs)
        assert "R1" in delta.new_analyses

    def test_timezone_aware_marker_and_naive_item(self):
        marker = "2026-08-28T12:00:00+00:00"
        recs = [_rec("R1", created_at="2026-08-28T14:00:00")]
        delta = compute_review_delta(last_review_timestamp=marker, records=recs)
        assert "R1" in delta.new_analyses

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx

        def _bad(*a, **k):
            raise AssertionError("Network!")

        monkeypatch.setattr(httpx.Client, "send", _bad)
        monkeypatch.setattr(socket, "create_connection", _bad)

        compute_review_delta(last_review_timestamp="2026-08-28T12:00:00Z", records=[_rec("R1")])

    def test_inputs_not_mutated(self):
        import copy
        recs = [_rec("R1")]
        orig = copy.deepcopy(recs)
        compute_review_delta(last_review_timestamp="2026-08-28T10:00:00Z", records=recs)
        assert recs == orig

    def test_multiple_new_items_order_preserved(self):
        marker = "2026-08-28T10:00:00Z"
        recs = [
            _rec("R1", created_at="2026-08-28T11:00:00Z"),
            _rec("R2", created_at="2026-08-28T12:00:00Z"),
            _rec("R3", created_at="2026-08-28T13:00:00Z"),
        ]
        delta = compute_review_delta(last_review_timestamp=marker, records=recs)
        assert delta.new_analyses == ["R1", "R2", "R3"]

    def test_closed_status_counted_as_resolved_investigation(self):
        marker = "2026-08-28T10:00:00Z"
        q = [_queue("Q1", created_at="2026-08-28T09:00:00Z", status="CLOSED")]
        prev_q = {"Q1": "IN_REVIEW"}
        delta = compute_review_delta(last_review_timestamp=marker, queue_items=q, previous_queue_states=prev_q)
        assert delta.investigations_resolved == ["Q1"]

    def test_already_resolved_investigation_not_re_reported(self):
        marker = "2026-08-28T10:00:00Z"
        q = [_queue("Q1", status="RESOLVED")]
        prev_q = {"Q1": "RESOLVED"}
        delta = compute_review_delta(last_review_timestamp=marker, queue_items=q, previous_queue_states=prev_q)
        assert delta.investigations_resolved == []

    def test_status_triggered_on_watchlist_eval_counted(self):
        marker = "2026-08-28T10:00:00Z"
        wl_evals = [{"watchlist_id": "WL-9", "status": "TRIGGERED", "created_at": "2026-08-28T12:00:00Z"}]
        delta = compute_review_delta(last_review_timestamp=marker, watchlist_evaluations=wl_evals)
        assert delta.watchlists_newly_triggered == ["WL-9"]

    def test_dismissed_alert_state_change_tracked(self):
        marker = "2026-08-28T10:00:00Z"
        alerts = [_alert("A1", status="DISMISSED")]
        prev = {"A1": "ACTIVE"}
        delta = compute_review_delta(last_review_timestamp=marker, alerts=alerts, previous_alert_states=prev)
        assert len(delta.alerts_changed_state) == 1
        assert delta.alerts_changed_state[0]["new"] == "DISMISSED"

    def test_object_with_to_dict_method_supported(self):
        class Obj:
            def to_dict(self):
                return {"analysis_id": "OBJ-1", "created_at": "2026-08-28T15:00:00Z"}
        marker = "2026-08-28T12:00:00Z"
        delta = compute_review_delta(last_review_timestamp=marker, records=[Obj()])
        assert delta.new_analyses == ["OBJ-1"]

    def test_exact_same_timestamp_not_considered_after(self):
        marker = "2026-08-28T12:00:00Z"
        recs = [_rec("R1", created_at="2026-08-28T12:00:00Z")]
        delta = compute_review_delta(last_review_timestamp=marker, records=recs)
        assert delta.new_analyses == []

    def test_has_changes_true_if_only_alerts_changed_state(self):
        marker = "2026-08-28T12:00:00Z"
        alerts = [_alert("A1", created_at="2026-08-28T09:00:00Z", status="RESOLVED")]
        prev = {"A1": "ACTIVE"}
        delta = compute_review_delta(last_review_timestamp=marker, alerts=alerts, previous_alert_states=prev)
        assert delta.has_changes is True

    def test_has_changes_true_if_only_investigation_resolved(self):
        marker = "2026-08-28T12:00:00Z"
        q = [_queue("Q1", created_at="2026-08-28T09:00:00Z", status="RESOLVED")]
        prev_q = {"Q1": "OPEN"}
        delta = compute_review_delta(last_review_timestamp=marker, queue_items=q, previous_queue_states=prev_q)
        assert delta.has_changes is True
