"""Phase 17 Invariant Suite.

Verifies strict invariants for all Phase 17 intelligence engines:
1. ZERO HTTP: All local intelligence operations produce 0 network requests.
2. IMMUTABILITY: AnalysisRecords and items remain unchanged before/after every operation.
3. DETERMINISM: Same input + same clock = exact same output and hashes.
4. RERUN SAFETY: Repeated evaluation creates no duplicate records or state corruption.
5. SECURITY: No credentials, tokens, secrets, or signed URLs are exposed.
6. RESPONSIBLE ANALYTICS: No causal, medical, or predictive assertions.
7. PROVENANCE: Every operational insight identifies its source.
8. CAPACITY: Session buffers remain bounded.
"""

from __future__ import annotations

import copy
import json
import pytest

from frontend.utils.alert_grouping import group_alerts
from frontend.utils.attention_score import compute_attention_score, rank_by_attention
from frontend.utils.clock import FrozenClock
from frontend.utils.export import generate_operational_decision_case_brief
from frontend.utils.latest_change import compute_latest_change
from frontend.utils.location_intelligence import build_location_summaries
from frontend.utils.observability import (
    MAX_OBSERVABILITY_EVENTS,
    clear_observability_events,
    get_observability_events,
    record_event,
    sanitize_observability_data,
)
from frontend.utils.operational_summary import build_operational_summary
from frontend.utils.operator_actions import generate_all_actions
from frontend.utils.pattern_detection import detect_all_patterns
from frontend.utils.responsible_analytics import check_prohibited_terms
from frontend.utils.review_delta import compute_review_delta


def _sample_records():
    return [
        {
            "analysis_id": "HI-001",
            "location_label": "Downtown Central",
            "date": "2026-08-27",
            "observed_temperature": 34.2,
            "data_quality": "HIGH",
            "metrics": {"mean_temp": 34.2, "temp_spread": 4.1, "total_tiles": 20},
        },
        {
            "analysis_id": "HI-002",
            "location_label": "Downtown Central",
            "date": "2026-08-28",
            "observed_temperature": 36.5,
            "data_quality": "HIGH",
            "metrics": {"mean_temp": 36.5, "temp_spread": 5.0, "total_tiles": 20},
        },
    ]


class TestPhase17Invariants:
    """Rigorous verification of Phase 17 architectural and operational invariants."""

    def test_invariant_zero_http_network_calls(self, monkeypatch):
        """Invariant 1: Zero network requests across all Phase 17 modules."""
        import socket
        import httpx

        def _fail_on_network(*args, **kwargs):
            raise AssertionError("CRITICAL INVARIANT VIOLATION: Network call attempted in local intelligence pipeline!")

        monkeypatch.setattr(httpx.Client, "send", _fail_on_network)
        monkeypatch.setattr(socket, "create_connection", _fail_on_network)

        recs = _sample_records()
        clk = FrozenClock("2026-08-28T12:00:00Z")

        # Execute every Phase 17 pure utility
        op_sum = build_operational_summary(records=recs, clock=clk)
        patterns = detect_all_patterns(records=recs)
        latest_ch = compute_latest_change(recs)
        loc_sums = build_location_summaries(recs)
        groups = group_alerts([{"alert_id": "A1", "analysis_id": "HI-001"}])
        scores = rank_by_attention([{"alert_id": "A1"}], clock=clk)
        actions = generate_all_actions(records=recs)
        delta = compute_review_delta("2026-08-27T10:00:00Z", records=recs, clock=clk)
        brief = generate_operational_decision_case_brief(source_record=recs[1], clock=clk)

        assert op_sum.completed_analyses == 2
        assert len(loc_sums) == 1
        assert len(brief) > 0

    def test_invariant_immutability_of_analysis_records(self):
        """Invariant 2: Source records are strictly preserved without in-place mutation."""
        recs = _sample_records()
        orig_recs = copy.deepcopy(recs)
        clk = FrozenClock("2026-08-28T12:00:00Z")

        build_operational_summary(records=recs, clock=clk)
        detect_all_patterns(records=recs)
        compute_latest_change(recs)
        build_location_summaries(recs)
        compute_review_delta("2026-08-27T10:00:00Z", records=recs, clock=clk)
        generate_operational_decision_case_brief(source_record=recs[0], clock=clk)

        assert recs == orig_recs

    def test_invariant_determinism(self):
        """Invariant 3: Same input + same clock produces identical outputs and hashes."""
        recs = _sample_records()
        clk = FrozenClock("2026-08-28T12:00:00Z")

        s1 = build_operational_summary(records=recs, clock=clk)
        s2 = build_operational_summary(records=recs, clock=clk)
        assert s1.to_dict() == s2.to_dict()

        ch1 = compute_latest_change(recs)
        ch2 = compute_latest_change(recs)
        assert ch1.to_dict() == ch2.to_dict()

        p1 = detect_all_patterns(records=recs)
        p2 = detect_all_patterns(records=recs)
        assert [p.to_dict() for p in p1] == [p.to_dict() for p in p2]

        brief1 = generate_operational_decision_case_brief(source_record=recs[1], clock=clk)
        brief2 = generate_operational_decision_case_brief(source_record=recs[1], clock=clk)
        assert brief1 == brief2

    def test_invariant_security_secret_sanitization(self):
        """Invariant 4: Sensitive keys, tokens, and signed URLs are never leaked in exports or telemetry."""
        dirty_record = {
            "analysis_id": "HI-SECRET-01",
            "api_key": "fortyguard_live_secret_key_12345",
            "auth_token": "bearer eyJhbGciOi...",
            "download_url": "https://s3.amazonaws.com/bucket/report.pdf?X-Amz-Signature=abcdef123456",
            "metrics": {"mean_temp": 33.0},
        }

        # Test export sanitization
        brief_json = generate_operational_decision_case_brief(source_record=dirty_record, format="json")
        assert "fortyguard_live_secret_key_12345" not in brief_json
        assert "X-Amz-Signature" not in brief_json
        assert "[REDACTED" in brief_json or "api_key" not in brief_json

        # Test observability sanitization
        cleaned_meta = sanitize_observability_data(dirty_record)
        assert cleaned_meta["api_key"] == "[REDACTED]"
        assert cleaned_meta["auth_token"] == "[REDACTED]"
        assert "[REDACTED" in cleaned_meta["download_url"]

    def test_invariant_responsible_analytics_no_forbidden_terms(self):
        """Invariant 5: All generated text strictly obeys Responsible Analytics standards."""
        recs = _sample_records()
        clk = FrozenClock("2026-08-28T12:00:00Z")

        op_sum = build_operational_summary(records=recs, clock=clk)
        assert check_prohibited_terms(op_sum.summary_narrative) == []

        patterns = detect_all_patterns(records=recs)
        for p in patterns:
            assert check_prohibited_terms(p.explanation) == []
            for ev in p.evidence:
                assert check_prohibited_terms(ev) == []

        actions = generate_all_actions(records=recs)
        for act in actions:
            assert check_prohibited_terms(f"{act.title} {act.reason}") == []

        brief = generate_operational_decision_case_brief(source_record=recs[0], clock=clk)
        assert check_prohibited_terms(brief) == []

    def test_invariant_provenance_traceability(self):
        """Invariant 6: Every operational insight and brief includes provenance metadata."""
        recs = _sample_records()
        clk = FrozenClock("2026-08-28T12:00:00Z")

        brief_json_str = generate_operational_decision_case_brief(source_record=recs[0], format="json", clock=clk)
        payload = json.loads(brief_json_str)

        assert "provenance" in payload
        assert payload["provenance"]["system_source"] == "FortyGuard Heat Intelligence Decision Engine"
        assert payload["provenance"]["canonical_hash"] is not None
        assert "2026-08-28" in payload["provenance"]["generated_at"]

    def test_invariant_capacity_bounded_buffers(self):
        """Invariant 7: Observability and event queues are bounded with FIFO eviction."""
        clear_observability_events()
        for i in range(MAX_OBSERVABILITY_EVENTS + 50):
            record_event(
                event_name="pattern_detected",
                analysis_id=f"HI-{i}",
                status="SUCCESS",
            )

        events = get_observability_events(limit=1000)
        assert len(events) <= MAX_OBSERVABILITY_EVENTS
        clear_observability_events()
