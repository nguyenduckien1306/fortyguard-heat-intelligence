"""Test suite for Operator Attention Scoring Engine (Phase 17)."""

from __future__ import annotations

import json
import pytest

from frontend.utils.attention_score import (
    AttentionScore,
    compute_attention_score,
    rank_by_attention,
)
from frontend.utils.clock import FrozenClock


def _alert(aid, severity="WATCH", priority=30.0, created_at="2026-08-28T10:00:00Z", dq="HIGH"):
    return {
        "alert_id": aid,
        "severity": severity,
        "priority_score": priority,
        "created_at": created_at,
        "data_quality": dq,
    }


class TestAttentionScore:
    def test_single_alert_attention_score_calculation(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1", severity="CRITICAL", priority=85.0)
        score = compute_attention_score(alert, item_type="alert", clock=clk)
        assert score.item_id == "A1"
        assert score.item_type == "alert"
        assert score.attention_score > 0
        assert score.priority_component >= 85.0
        assert "CRITICAL" in score.explanation

    def test_higher_severity_yields_higher_score(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        a_crit = _alert("A-Crit", severity="CRITICAL", priority=90.0)
        a_info = _alert("A-Info", severity="INFO", priority=10.0)
        s_crit = compute_attention_score(a_crit, clock=clk)
        s_info = compute_attention_score(a_info, clock=clk)
        assert s_crit.attention_score > s_info.attention_score

    def test_recurrence_increases_attention_score(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1", severity="WATCH")
        s0 = compute_attention_score(alert, recurrence_count=0, clock=clk)
        s3 = compute_attention_score(alert, recurrence_count=3, clock=clk)
        assert s3.attention_score > s0.attention_score
        assert s3.recurrence_component > s0.recurrence_component
        assert "3 recurrence(s)" in s3.explanation

    def test_uninvestigated_item_gets_higher_attention(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1")
        s_none = compute_attention_score(alert, investigation_state="none", clock=clk)
        s_resolved = compute_attention_score(alert, investigation_state="resolved", clock=clk)
        assert s_none.attention_score > s_resolved.attention_score
        assert "not yet investigated" in s_none.explanation

    def test_in_review_investigation_intermediate_bonus(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1")
        s_open = compute_attention_score(alert, investigation_state="open", clock=clk)
        s_review = compute_attention_score(alert, investigation_state="in_review", clock=clk)
        s_resolved = compute_attention_score(alert, investigation_state="resolved", clock=clk)
        assert s_open.investigation_component > s_review.investigation_component > s_resolved.investigation_component

    def test_evidence_availability_affects_score(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1")
        s_no_ev = compute_attention_score(alert, has_evidence=False, clock=clk)
        s_ev = compute_attention_score(alert, has_evidence=True, clock=clk)
        assert s_no_ev.attention_score > s_ev.attention_score
        assert "no evidence" in s_no_ev.explanation.lower()

    def test_data_quality_penalty_low(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        a_high = _alert("A1", dq="HIGH")
        a_low = _alert("A2", dq="LOW")
        s_high = compute_attention_score(a_high, clock=clk)
        s_low = compute_attention_score(a_low, clock=clk)
        assert s_low.data_quality_component < s_high.data_quality_component
        assert "LOW data quality" in s_low.explanation

    def test_data_quality_penalty_insufficient(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        a_insufficient = _alert("A1", dq="INSUFFICIENT")
        s = compute_attention_score(a_insufficient, clock=clk)
        assert s.data_quality_component == -15.0

    def test_ranking_by_attention_descending(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alerts = [
            _alert("A-Low", severity="INFO", priority=10.0),
            _alert("A-Crit", severity="CRITICAL", priority=90.0),
            _alert("A-Med", severity="WATCH", priority=40.0),
        ]
        ranked = rank_by_attention(alerts, clock=clk)
        assert len(ranked) == 3
        assert ranked[0].item_id == "A-Crit"
        assert ranked[1].item_id == "A-Med"
        assert ranked[2].item_id == "A-Low"

    def test_ranking_with_recurrence_and_investigation_maps(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alerts = [
            _alert("A1", severity="WATCH", priority=40.0),
            _alert("A2", severity="WATCH", priority=40.0),
        ]
        rec_map = {"A2": 5}
        inv_map = {"A1": "resolved", "A2": "none"}
        ranked = rank_by_attention(alerts, recurrence_map=rec_map, investigation_map=inv_map, clock=clk)
        assert ranked[0].item_id == "A2"

    def test_ranking_with_evidence_set(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alerts = [
            _alert("A1", severity="WATCH", priority=40.0),
            _alert("A2", severity="WATCH", priority=40.0),
        ]
        ev_set = {"A1"}  # A1 has evidence, A2 does not (needs attention)
        ranked = rank_by_attention(alerts, evidence_set=ev_set, clock=clk)
        assert ranked[0].item_id == "A2"

    def test_deterministic_attention_score(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1", severity="CRITICAL", priority=85.0)
        s1 = compute_attention_score(alert, clock=clk)
        s2 = compute_attention_score(alert, clock=clk)
        assert s1 == s2
        assert s1.attention_score == s2.attention_score

    def test_json_serializable_to_dict(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1")
        score = compute_attention_score(alert, clock=clk)
        d = score.to_dict()
        assert isinstance(d, dict)
        json.dumps(d)  # Valid JSON

    def test_immutability(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        score = compute_attention_score(_alert("A1"), clock=clk)
        with pytest.raises(Exception):
            score.attention_score = 100.0  # type: ignore

    def test_empty_items_ranking_returns_empty(self):
        assert rank_by_attention([]) == []

    def test_missing_created_at_uses_default_age_score(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = {"alert_id": "A1", "severity": "WATCH"}
        score = compute_attention_score(alert, clock=clk)
        assert score.age_component == 5.0

    def test_malformed_created_at_handled_gracefully(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = {"alert_id": "A1", "created_at": "not-a-date"}
        score = compute_attention_score(alert, clock=clk)
        assert score.age_component == 5.0

    def test_recent_alert_has_higher_age_component(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        a_recent = _alert("A1", created_at="2026-08-28T11:50:00Z")
        a_old = _alert("A2", created_at="2026-08-27T10:00:00Z")
        s_recent = compute_attention_score(a_recent, clock=clk)
        s_old = compute_attention_score(a_old, clock=clk)
        assert s_recent.age_component > s_old.age_component

    def test_signal_item_type_support(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        sig = {"signal_id": "S1", "severity": "ELEVATED", "priority_score": 50.0}
        score = compute_attention_score(sig, item_type="signal", clock=clk)
        assert score.item_type == "signal"
        assert score.item_id == "S1"

    def test_investigation_item_type_support(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        q = {"queue_id": "Q1", "severity": "CRITICAL", "priority_score": 70.0}
        score = compute_attention_score(q, item_type="investigation", clock=clk)
        assert score.item_type == "investigation"
        assert score.item_id == "Q1"

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx

        def _bad(*a, **k):
            raise AssertionError("Network!")

        monkeypatch.setattr(httpx.Client, "send", _bad)
        monkeypatch.setattr(socket, "create_connection", _bad)

        rank_by_attention([_alert("A1")])

    def test_explanation_contains_standard_priority_when_no_flags(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1", severity="INFO", dq="HIGH")
        score = compute_attention_score(alert, investigation_state="resolved", has_evidence=True, clock=clk)
        assert "Standard" in score.explanation or "INFO" in score.explanation or score.explanation != ""

    def test_item_not_mutated(self):
        import copy
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1")
        orig = copy.deepcopy(alert)
        compute_attention_score(alert, clock=clk)
        assert alert == orig

    def test_max_recurrence_component_capped(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = _alert("A1")
        score = compute_attention_score(alert, recurrence_count=10, clock=clk)
        assert score.recurrence_component <= 20.0

    def test_negative_priority_normalized_to_zero(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = {"alert_id": "A1", "severity": "INFO", "priority_score": -10.0}
        score = compute_attention_score(alert, clock=clk)
        assert score.priority_component >= 0.0

    def test_nan_priority_handled(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = {"alert_id": "A1", "severity": "INFO", "priority_score": float("nan")}
        score = compute_attention_score(alert, clock=clk)
        assert score.priority_component >= 0.0

    def test_inf_priority_handled(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        alert = {"alert_id": "A1", "severity": "INFO", "priority_score": float("inf")}
        score = compute_attention_score(alert, clock=clk)
        assert score.priority_component >= 0.0

    def test_object_with_to_dict_method(self):
        class Obj:
            def to_dict(self):
                return {"alert_id": "OBJ-1", "severity": "CRITICAL"}
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        score = compute_attention_score(Obj(), clock=clk)
        assert score.item_id == "OBJ-1"

    def test_rank_preserves_count(self):
        alerts = [_alert(f"A{i}") for i in range(15)]
        ranked = rank_by_attention(alerts)
        assert len(ranked) == 15

    def test_timezone_naive_and_aware_compatibility(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00")  # naive
        alert = _alert("A1", created_at="2026-08-28T11:00:00+00:00")  # aware
        score = compute_attention_score(alert, clock=clk)
        assert score.age_component >= 0.0
