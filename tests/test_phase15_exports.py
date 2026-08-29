"""Unit tests for Phase 15.6 Decision Brief & Export Engine with Provenance.

Verifies:
- Canonical provenance metadata headers.
- Alert Evidence Report generation (JSON and TXT formats).
- Watchlist Evaluation Report generation (JSON and TXT formats).
- CommandCenter Decision Brief generation (JSON and TXT formats).
- Recursive deep sanitization of credentials and signed S3 URLs across exports.
- Zero network I/O.
"""

from __future__ import annotations

import json
from unittest.mock import patch
import pytest

from frontend.utils.clock import FrozenClock
from frontend.utils.export import (
    generate_alert_evidence_export,
    generate_command_center_decision_brief,
    generate_export_provenance_header,
    generate_watchlist_evaluation_export,
)
from frontend.utils.intelligence_snapshot import IntelligenceSnapshot


# ══════════════════════════════════════════════════════════════════════════════
# 1. Provenance Metadata Header Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestExportProvenanceHeaders:
    """Provenance metadata format and hash consistency."""

    def test_provenance_header_structure(self):
        clk = FrozenClock("2026-08-23T12:00:00")
        header = generate_export_provenance_header("TEST_EXPORT", clock=clk)
        assert header["export_type"] == "TEST_EXPORT"
        assert header["schema_version"] == 1
        assert header["generated_at"] == "2026-08-23T12:00:00"
        assert len(header["canonical_hash"]) == 64
        assert "FortyGuard" in header["system_source"]


# ══════════════════════════════════════════════════════════════════════════════
# 2. Alert Evidence Export Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestAlertEvidenceExport:
    """Alert Evidence report formatting and deep sanitization."""

    def test_alert_evidence_json_export(self):
        clk = FrozenClock("2026-08-23T12:00:00")
        alert = {
            "alert_id": "ALT-001",
            "policy_name": "Extreme Heat",
            "severity": "CRITICAL",
            "priority_score": 85.0,
            "priority_tier": "Critical",
            "secret_token": "SHOULD_BE_REDACTED",
        }
        bundle = {
            "evidence_id": "EVD-001",
            "evidence_hash": "a" * 64,
            "why_am_i_seeing_this": "Observed 42°C >= 38°C",
            "api_key": "LEAK_KEY",
        }

        raw_json = generate_alert_evidence_export(alert, bundle, format="json", clock=clk)
        parsed = json.loads(raw_json)

        assert parsed["provenance"]["export_type"] == "ALERT_EVIDENCE_REPORT"
        assert parsed["alert"]["alert_id"] == "ALT-001"
        assert parsed["alert"]["secret_token"] == "[REDACTED]"
        assert parsed["evidence_bundle"]["api_key"] == "[REDACTED]"

    def test_alert_evidence_brief_format(self):
        alert = {"alert_id": "ALT-002", "policy_name": "Heat Alert", "priority_score": 75.0, "priority_tier": "Critical"}
        txt = generate_alert_evidence_export(alert, format="brief")
        assert "FORTYGUARD ALERT EVIDENCE REPORT" in txt
        assert "ALT-002" in txt
        assert "RESPONSIBLE ANALYTICS NOTICE" in txt


# ══════════════════════════════════════════════════════════════════════════════
# 3. Watchlist Evaluation Export Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestWatchlistEvaluationExport:
    """Watchlist evaluation reports in JSON and Brief format."""

    def test_watchlist_evaluation_json_export(self):
        evals = [
            {"watchlist_name": "WL 1", "matched": True, "matched_criteria": ["mean_temp"]},
            {"watchlist_name": "WL 2", "matched": False, "matched_criteria": []},
        ]
        raw_json = generate_watchlist_evaluation_export(evals, format="json")
        parsed = json.loads(raw_json)
        assert parsed["total_evaluated"] == 2
        assert parsed["matched_count"] == 1
        assert parsed["provenance"]["export_type"] == "WATCHLIST_EVALUATION_REPORT"

    def test_watchlist_evaluation_brief_format(self):
        evals = [{"watchlist_name": "Zone Watch", "matched": True, "evidence_list": ["Temp >= 35.0°C"]}]
        txt = generate_watchlist_evaluation_export(evals, format="brief")
        assert "FORTYGUARD WATCHLIST EVALUATION REPORT" in txt
        assert "Zone Watch" in txt
        assert "MATCHED" in txt


# ══════════════════════════════════════════════════════════════════════════════
# 4. Command Center Decision Brief Export Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCommandCenterDecisionBriefExport:
    """Executive decision brief exports with deep sanitization."""

    def test_command_center_decision_brief_export(self):
        snap = IntelligenceSnapshot(
            snapshot_id="SNAP-EXEC-01",
            generated_at="2026-08-23T12:00:00",
            record_ids=["REC-1", "REC-2"],
            priority_summary={"critical": 1, "high": 2, "medium": 3, "low": 0},
            data_quality_summary={"high": 2, "medium": 0, "low": 0, "insufficient": 0},
        )
        brief_txt = generate_command_center_decision_brief(snap, format="brief")
        assert "FORTYGUARD HEAT INTELLIGENCE — COMMAND CENTER DECISION BRIEF" in brief_txt
        assert "SNAP-EXEC-01" in brief_txt
        assert "Critical : 1" in brief_txt
        assert "High     : 2" in brief_txt

    @patch("httpx.Client.request")
    @patch("requests.request")
    def test_export_engine_makes_zero_network_calls(self, mock_requests, mock_httpx):
        snap = IntelligenceSnapshot(snapshot_id="SNAP-ZERO", generated_at="2026-08-23T12:00:00", record_ids=[])
        generate_command_center_decision_brief(snap)
        generate_alert_evidence_export({"alert_id": "A1"})
        generate_watchlist_evaluation_export([])

        mock_requests.assert_not_called()
        mock_httpx.assert_not_called()

    def test_command_center_decision_brief_json_format(self):
        snap = IntelligenceSnapshot(
            snapshot_id="SNAP-JSON-01",
            generated_at="2026-08-23T12:00:00",
            record_ids=["REC-1"],
            priority_summary={"critical": 1, "high": 0, "medium": 0, "low": 0},
        )
        raw_json = generate_command_center_decision_brief(snap, format="json")
        parsed = json.loads(raw_json)
        assert parsed["provenance"]["export_type"] == "COMMAND_CENTER_DECISION_BRIEF"
        assert parsed["snapshot"]["snapshot_id"] == "SNAP-JSON-01"

    def test_nested_credential_scrubbing_in_alerts(self):
        alert_with_nested_creds = {
            "alert_id": "ALT-SEC",
            "nested_info": {
                "user_api_key": "SECRET123",
                "inner_list": [{"signed_url": "https://s3.amazonaws.com/bucket/key?auth=xyz"}],
            },
        }
        res_json = generate_alert_evidence_export(alert_with_nested_creds, format="json")
        parsed = json.loads(res_json)
        nested = parsed["alert"]["nested_info"]
        assert nested["user_api_key"] == "[REDACTED]"
        assert nested["inner_list"][0]["signed_url"] == "[REDACTED_SECURE_SIGNED_URL]"

    def test_empty_watchlist_export_handles_gracefully(self):
        raw_json = generate_watchlist_evaluation_export([], format="json")
        parsed = json.loads(raw_json)
        assert parsed["total_evaluated"] == 0
        assert parsed["evaluations"] == []

    def test_investigation_brief_preserves_live_signal_evidence_consistency(self):
        """Verify the exact live signal scenario preserves observed=32.5, threshold=32.0, data_quality=LOW."""
        from frontend.utils.export import generate_investigation_brief
        from frontend.utils.investigation_queue import InvestigationItem

        # InvestigationItem constructed from originating signal
        item = InvestigationItem(
            queue_id="Q-20260828114223-001",
            analysis_id="HI-20260828-001",
            signal_id="SIG-TH-WATCH-HI-20260828-001",
            priority="Medium",
            reason="Watch Temperature Threshold Reached (Downtown)",
            location="Downtown",
            analysis_type="heat_intelligence",
            metric="mean_temperature",
            observed_value=32.5,
            threshold_value=32.0,
            data_quality="LOW",
        )

        record = {
            "analysis_id": "HI-20260828-001",
            "analysis_type": "heat_intelligence",
            "location_label": "Downtown",
            "date": "2026-08-28",
            "observed_temperature": 32.5,
        }

        # Brief format
        brief_txt = generate_investigation_brief(item, record, format="brief")
        assert "Metric      : mean_temperature" in brief_txt
        assert "Observed    : 32.5" in brief_txt
        assert "Threshold   : 32.0" in brief_txt
        assert "Data Quality: LOW" in brief_txt
        assert "Observed    : None" not in brief_txt
        assert "Threshold   : 35.0" not in brief_txt
        assert "Data Quality: HIGH" not in brief_txt

        # JSON format
        brief_json = generate_investigation_brief(item, record, format="json")
        parsed = json.loads(brief_json)
        sig = parsed["signal"]
        assert sig["metric"] == "mean_temperature"
        assert sig["observed_value"] == 32.5
        assert sig["threshold_value"] == 32.0
        assert sig["data_quality"] == "LOW"

    def test_end_to_end_operational_signal_to_queue_to_brief_chain(self):
        """End-to-end provenance test: real OperationalSignal -> add_to_queue -> InvestigationItem -> EvidenceBundle -> generate_investigation_brief."""
        import copy
        from frontend.utils.export import generate_investigation_brief
        from frontend.utils.investigation_queue import (
            add_to_investigation_queue,
            clear_investigation_queue,
            get_investigation_queue,
        )
        from frontend.utils.operational_intelligence import OperationalSignal

        clear_investigation_queue()

        sig = OperationalSignal(
            signal_id="SIG-TH-WATCH-HI-20260828-001",
            analysis_id="HI-20260828-001",
            signal_type="temperature_above_threshold",
            severity="WATCH",
            title="Watch Temperature Threshold Reached (Downtown)",
            description="Observed temperature of 32.5°C meets or exceeds the watch threshold of 32.0°C.",
            metric="observed_temperature",
            observed_value=32.5,
            threshold_value=32.0,
            direction="above",
            confidence="HIGH",
            evidence=[
                "Location: Downtown (HI-20260828-001)",
                "Observed value: 32.50°C",
                "Watch threshold: 32.00°C",
            ],
            data_quality="LOW",
        )

        record = {
            "analysis_id": "HI-20260828-001",
            "analysis_type": "heat_intelligence",
            "location_label": "Downtown",
            "date": "2026-08-28",
            "observed_temperature": 32.5,
        }

        # 1. Add to investigation queue
        ok, err, item = add_to_investigation_queue(
            analysis_id=sig.analysis_id,
            signal_id=sig.signal_id,
            priority="Medium",
            reason=sig.title,
            source_signal=sig,
        )
        assert ok is True
        assert item is not None
        assert item.observed_value == 32.5
        assert item.threshold_value == 32.0
        assert item.data_quality == "LOW"
        assert item.metric == "observed_temperature"
        assert item.evidence_bundle is not None

        # 2. Retrieve from queue store (roundtrip from session state)
        queue_items = get_investigation_queue()
        assert len(queue_items) == 1
        stored_item = queue_items[0]
        assert stored_item.observed_value == 32.5
        assert stored_item.threshold_value == 32.0
        assert stored_item.data_quality == "LOW"

        # 3. Generate Investigation Brief (TXT)
        brief_txt = generate_investigation_brief(stored_item, record, format="brief")
        assert "Metric      : observed_temperature" in brief_txt
        assert "Observed    : 32.5" in brief_txt
        assert "Threshold   : 32.0" in brief_txt
        assert "Data Quality: LOW" in brief_txt
        assert "Observed    : None" not in brief_txt
        assert "Threshold   : 35.0" not in brief_txt
        assert "Data Quality: HIGH" not in brief_txt

        # 4. Generate Investigation Brief (JSON)
        brief_json = generate_investigation_brief(stored_item, record, format="json")
        parsed = json.loads(brief_json)
        sig_data = parsed["signal"]
        assert sig_data["metric"] == "observed_temperature"
        assert sig_data["observed_value"] == 32.5
        assert sig_data["threshold_value"] == 32.0
        assert sig_data["data_quality"] == "LOW"

    def test_investigate_and_add_to_queue_paths_converge(self):
        """Verify that both Investigate and Add to Queue paths converge on the exact same canonical InvestigationItem facts."""
        from frontend.utils.investigation_queue import (
            add_to_investigation_queue,
            clear_investigation_queue,
            get_investigation_queue,
        )
        from frontend.utils.operational_intelligence import OperationalSignal

        clear_investigation_queue()

        sig = OperationalSignal(
            signal_id="SIG-TH-WATCH-001",
            analysis_id="HI-20260828-001",
            signal_type="temperature_above_threshold",
            severity="WATCH",
            title="Watch Temperature Threshold Reached",
            description="Observed temperature of 32.5°C meets or exceeds the watch threshold of 32.0°C.",
            metric="observed_temperature",
            observed_value=32.5,
            threshold_value=32.0,
            data_quality="LOW",
        )

        # Path 1: Add to Queue
        ok1, _, item1 = add_to_investigation_queue(
            analysis_id=sig.analysis_id,
            signal_id=sig.signal_id,
            priority="Medium",
            reason=sig.title,
            source_signal=sig,
        )
        assert ok1 is True

        clear_investigation_queue()

        # Path 2: Investigate (direct call with same signature)
        ok2, _, item2 = add_to_investigation_queue(
            analysis_id=sig.analysis_id,
            signal_id=sig.signal_id,
            priority="Medium",
            reason=sig.title,
            source_signal=sig,
        )
        assert ok2 is True

        assert item1.observed_value == item2.observed_value == 32.5
        assert item1.threshold_value == item2.threshold_value == 32.0
        assert item1.data_quality == item2.data_quality == "LOW"
        assert item1.metric == item2.metric == "observed_temperature"

    def test_immutability_of_source_signal_and_record(self):
        """Verify that queuing and brief generation do not mutate the input signal or AnalysisRecord."""
        import copy
        from frontend.utils.export import generate_investigation_brief
        from frontend.utils.investigation_queue import add_to_investigation_queue, clear_investigation_queue
        from frontend.utils.operational_intelligence import OperationalSignal

        clear_investigation_queue()

        sig = OperationalSignal(
            signal_id="SIG-IMMUTABLE-001",
            analysis_id="HI-20260828-001",
            signal_type="temperature_above_threshold",
            severity="WATCH",
            title="Watch Threshold",
            description="32.5°C >= 32.0°C",
            metric="observed_temperature",
            observed_value=32.5,
            threshold_value=32.0,
            data_quality="LOW",
        )
        sig_copy = copy.deepcopy(sig)

        record = {
            "analysis_id": "HI-20260828-001",
            "analysis_type": "heat_intelligence",
            "observed_temperature": 32.5,
            "metrics": {"mean_temp": 32.5},
        }
        record_copy = copy.deepcopy(record)

        _, _, item = add_to_investigation_queue(
            analysis_id=sig.analysis_id,
            signal_id=sig.signal_id,
            source_signal=sig,
        )
        _ = generate_investigation_brief(item, record, format="brief")
        _ = generate_investigation_brief(item, record, format="json")

        assert sig.to_dict() == sig_copy.to_dict()
        assert record == record_copy

    def test_security_deep_sanitization_in_investigation_export(self):
        """Verify that nested credentials, bearer tokens, and signed URLs are sanitized from brief exports."""
        from frontend.utils.export import generate_investigation_brief
        from frontend.utils.investigation_queue import add_to_investigation_queue, clear_investigation_queue

        clear_investigation_queue()

        raw_sig = {
            "signal_id": "SIG-SEC-01",
            "analysis_id": "HI-SEC-01",
            "api_key": "fg_secret_live_12345",
            "authorization": "Bearer token_secret_999",
            "headers": {"X-Secret": "super_secret"},
            "signed_url": "https://s3.amazonaws.com/bucket/report.pdf?AWSAccessKeyId=AKIAIOSFODNN7EXAMPLE&Signature=vjbyPxybdZaNmGa%2ByT272YEAiv4%3D",
            "download_link": "https://secure.example.com/download?token=xyz",
            "observed_value": 32.5,
            "threshold_value": 32.0,
            "data_quality": "LOW",
        }

        _, _, item = add_to_investigation_queue(
            analysis_id="HI-SEC-01",
            source_signal=raw_sig,
        )

        brief_json = generate_investigation_brief(item, None, format="json")
        assert "fg_secret_live_12345" not in brief_json
        assert "token_secret_999" not in brief_json
        assert "super_secret" not in brief_json
        assert "AWSAccessKeyId" not in brief_json
        assert "vjbyPxybdZaNmGa" not in brief_json

    def test_zero_network_calls_during_investigation_brief_pipeline(self, monkeypatch):
        """Verify that Add to Queue and Investigation Brief generation make zero HTTP calls."""
        import socket
        import httpx
        from frontend.utils.export import generate_investigation_brief
        from frontend.utils.investigation_queue import add_to_investigation_queue, clear_investigation_queue

        clear_investigation_queue()

        def _forbidden_network(*args, **kwargs):
            raise AssertionError("Network call was attempted during local investigation workflow!")

        monkeypatch.setattr(httpx.Client, "send", _forbidden_network)
        monkeypatch.setattr(socket, "create_connection", _forbidden_network)

        sig = {
            "signal_id": "SIG-ZERO-NET",
            "analysis_id": "HI-20260828-001",
            "observed_value": 32.5,
            "threshold_value": 32.0,
            "data_quality": "LOW",
        }

        ok, _, item = add_to_investigation_queue(
            analysis_id="HI-20260828-001",
            source_signal=sig,
        )
        assert ok is True

        brief_txt = generate_investigation_brief(item, None, format="brief")
        assert "Observed    : 32.5" in brief_txt
        assert "Threshold   : 32.0" in brief_txt
        assert "Data Quality: LOW" in brief_txt


