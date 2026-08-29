"""Unit test suite for Operational Executive Summary Engine (Phase 17)."""

from __future__ import annotations

from dataclasses import dataclass
import pytest

from frontend.utils.clock import FrozenClock
from frontend.utils.operational_summary import (
    OperationalSummary,
    build_operational_summary,
)


@dataclass
class MockRecord:
    analysis_id: str
    location_label: str = "Downtown"
    analysis_type: str = "heatmap"
    date: str | None = "2026-08-28"
    status: str = "Completed"
    metrics: dict | None = None
    observed_temperature: float | None = None
    data_quality: str | None = "HIGH"

    def to_dict(self):
        return {
            "analysis_id": self.analysis_id,
            "location_label": self.location_label,
            "analysis_type": self.analysis_type,
            "date": self.date,
            "status": self.status,
            "metrics": self.metrics or {},
            "observed_temperature": self.observed_temperature,
            "data_quality": self.data_quality,
        }


@dataclass
class MockSignal:
    signal_id: str
    analysis_id: str
    severity: str = "CRITICAL"
    disposition: str = "NEW"

    def to_dict(self):
        return {
            "signal_id": self.signal_id,
            "analysis_id": self.analysis_id,
            "severity": self.severity,
            "disposition": self.disposition,
        }


@dataclass
class MockAlert:
    alert_id: str
    severity: str = "CRITICAL"
    priority: str = "Critical"
    status: str = "ACTIVE"

    def to_dict(self):
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "priority": self.priority,
            "status": self.status,
        }


@dataclass
class MockQueueItem:
    queue_id: str
    status: str = "OPEN"

    def to_dict(self):
        return {
            "queue_id": self.queue_id,
            "status": self.status,
        }


class TestOperationalSummary:
    """Test suite for build_operational_summary."""

    def test_empty_inputs_returns_clean_empty_state(self):
        summary = build_operational_summary()
        assert summary.has_data is False
        assert summary.completed_analyses == 0
        assert summary.active_watchlists == 0
        assert summary.triggered_watchlists == 0
        assert summary.active_signals == 0
        assert summary.unresolved_alerts == 0
        assert summary.high_priority_alerts == 0
        assert summary.investigations_open == 0
        assert summary.latest_analysis_date is None
        assert summary.earliest_analysis_date is None
        assert summary.locations_represented == []

    def test_single_heatmap_record_summary(self):
        rec = MockRecord(analysis_id="HM-001", location_label="Harbor Point", date="2026-08-25")
        summary = build_operational_summary(records=[rec])
        assert summary.has_data is True
        assert summary.completed_analyses == 1
        assert summary.locations_represented == ["Harbor Point"]
        assert summary.latest_analysis_date == "2026-08-25"
        assert summary.earliest_analysis_date == "2026-08-25"
        assert summary.analysis_types["heatmap"] == 1
        assert summary.analysis_types["heat_intelligence"] == 0

    def test_single_heat_intelligence_record_summary(self):
        rec = MockRecord(
            analysis_id="HI-001",
            location_label="Midtown",
            analysis_type="heat_intelligence",
            date="2026-08-26",
            observed_temperature=33.5,
        )
        summary = build_operational_summary(records=[rec])
        assert summary.completed_analyses == 1
        assert summary.analysis_types["heat_intelligence"] == 1
        assert summary.locations_represented == ["Midtown"]

    def test_multiple_analyses_date_range_sorting(self):
        recs = [
            MockRecord(analysis_id="R1", date="2026-08-20"),
            MockRecord(analysis_id="R2", date="2026-08-28"),
            MockRecord(analysis_id="R3", date="2026-08-15"),
        ]
        summary = build_operational_summary(records=recs)
        assert summary.completed_analyses == 3
        assert summary.earliest_analysis_date == "2026-08-15"
        assert summary.latest_analysis_date == "2026-08-28"

    def test_distinct_locations_deduplicated_and_sorted(self):
        recs = [
            MockRecord(analysis_id="R1", location_label="Zone C"),
            MockRecord(analysis_id="R2", location_label="Zone A"),
            MockRecord(analysis_id="R3", location_label="Zone C"),
            MockRecord(analysis_id="R4", location_label="Zone B"),
        ]
        summary = build_operational_summary(records=recs)
        assert summary.locations_represented == ["Zone A", "Zone B", "Zone C"]

    def test_active_and_triggered_watchlists(self):
        wls = [{"watchlist_id": "WL-1"}, {"watchlist_id": "WL-2"}, {"watchlist_id": "WL-3"}]
        evals = [
            {"watchlist_id": "WL-1", "matched": True},
            {"watchlist_id": "WL-2", "matched": False},
            {"watchlist_id": "WL-3", "status": "TRIGGERED"},
        ]
        summary = build_operational_summary(watchlists=wls, watchlist_evaluations=evals)
        assert summary.active_watchlists == 3
        assert summary.triggered_watchlists == 2

    def test_active_vs_resolved_signals_count(self):
        sigs = [
            MockSignal("S1", "R1", severity="CRITICAL", disposition="NEW"),
            MockSignal("S2", "R1", severity="ELEVATED", disposition="ACKNOWLEDGED"),
            MockSignal("S3", "R2", severity="WATCH", disposition="RESOLVED"),
            MockSignal("S4", "R2", severity="INFO", disposition="DISMISSED"),
        ]
        summary = build_operational_summary(signals=sigs)
        assert summary.active_signals == 2
        assert summary.severity_distribution["CRITICAL"] == 1
        assert summary.severity_distribution["ELEVATED"] == 1
        assert summary.severity_distribution["WATCH"] == 1
        assert summary.severity_distribution["INFO"] == 1

    def test_unresolved_and_high_priority_alerts_count(self):
        alerts = [
            MockAlert("A1", severity="CRITICAL", status="ACTIVE"),
            MockAlert("A2", severity="ELEVATED", status="ACTIVE"),
            MockAlert("A3", severity="WATCH", status="ACTIVE", priority="Normal"),
            MockAlert("A4", severity="CRITICAL", status="RESOLVED"),
            MockAlert("A5", severity="CRITICAL", status="COOLING_DOWN"),
        ]
        summary = build_operational_summary(alerts=alerts)
        assert summary.unresolved_alerts == 3
        assert summary.high_priority_alerts == 2

    def test_investigation_queue_status_breakdown(self):
        q = [
            MockQueueItem("Q1", status="OPEN"),
            MockQueueItem("Q2", status="OPEN"),
            MockQueueItem("Q3", status="IN_REVIEW"),
            MockQueueItem("Q4", status="RESOLVED"),
        ]
        summary = build_operational_summary(queue_items=q)
        assert summary.investigations_open == 2
        assert summary.investigations_in_review == 1
        assert summary.investigations_resolved == 1

    def test_data_quality_distribution(self):
        recs = [
            MockRecord("R1", data_quality="HIGH"),
            MockRecord("R2", data_quality="MEDIUM"),
            MockRecord("R3", data_quality="LOW"),
            MockRecord("R4", data_quality="INSUFFICIENT"),
            MockRecord("R5", data_quality="HIGH"),
        ]
        summary = build_operational_summary(records=recs)
        assert summary.data_quality_distribution["HIGH"] == 2
        assert summary.data_quality_distribution["MEDIUM"] == 1
        assert summary.data_quality_distribution["LOW"] == 1
        assert summary.data_quality_distribution["INSUFFICIENT"] == 1

    def test_clock_injection_deterministic_timestamp(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        summary = build_operational_summary(clock=clk)
        assert "2026-08-28T12:00:00" in summary.generated_at

    def test_to_dict_and_from_dict_roundtrip(self):
        clk = FrozenClock(frozen_time="2026-08-28T12:00:00Z")
        recs = [MockRecord("R1", location_label="Downtown")]
        summary = build_operational_summary(records=recs, clock=clk)

        d = summary.to_dict()
        restored = OperationalSummary.from_dict(d)
        assert restored == summary
        assert restored.completed_analyses == 1
        assert restored.locations_represented == ["Downtown"]

    def test_distinguishes_no_data_from_zero_dates(self):
        summary_empty = build_operational_summary([])
        assert summary_empty.latest_analysis_date is None
        assert summary_empty.earliest_analysis_date is None
        assert summary_empty.completed_analyses == 0

    def test_malformed_record_without_date_or_location(self):
        bad_rec = {"analysis_id": "BAD-1"}
        summary = build_operational_summary(records=[bad_rec])
        assert summary.completed_analyses == 1
        assert summary.latest_analysis_date is None
        assert summary.locations_represented == []

    def test_malformed_record_with_whitespace_location(self):
        bad_rec = {"analysis_id": "BAD-2", "location_label": "   "}
        summary = build_operational_summary(records=[bad_rec])
        assert summary.locations_represented == []

    def test_record_status_filtering_ignores_processing_and_failed(self):
        recs = [
            {"analysis_id": "R1", "status": "Completed"},
            {"analysis_id": "R2", "status": "Processing"},
            {"analysis_id": "R3", "status": "Failed"},
        ]
        summary = build_operational_summary(records=recs)
        assert summary.completed_analyses == 1

    def test_narrative_generation_empty(self):
        summary = build_operational_summary()
        assert "No completed analyses" in summary.summary_narrative

    def test_narrative_generation_with_alerts_and_queue(self):
        recs = [MockRecord("R1", location_label="Downtown")]
        alerts = [MockAlert("A1", severity="CRITICAL", status="ACTIVE")]
        q = [MockQueueItem("Q1", status="OPEN")]
        summary = build_operational_summary(records=recs, alerts=alerts, queue_items=q)
        assert "1 completed analyses" in summary.summary_narrative
        assert "1 unresolved alert(s)" in summary.summary_narrative
        assert "1 open" in summary.summary_narrative

    def test_disclaimer_present_in_summary(self):
        summary = build_operational_summary()
        assert "Responsible Analytics" in summary.disclaimer or "causation" in summary.disclaimer.lower()

    def test_large_number_of_records_aggregation(self):
        recs = [MockRecord(f"R-{i}", location_label=f"Loc-{i%5}", date=f"2026-08-{10 + (i%15):02d}") for i in range(50)]
        summary = build_operational_summary(records=recs)
        assert summary.completed_analyses == 50
        assert len(summary.locations_represented) == 5

    def test_non_standard_signal_severity_mapping(self):
        sigs = [
            {"signal_id": "S1", "severity": "high", "disposition": "NEW"},
            {"signal_id": "S2", "severity": "medium", "disposition": "NEW"},
            {"signal_id": "S3", "severity": "low", "disposition": "NEW"},
        ]
        summary = build_operational_summary(signals=sigs)
        assert summary.severity_distribution["ELEVATED"] == 1
        assert summary.severity_distribution["WATCH"] == 1
        assert summary.severity_distribution["INFO"] == 1

    def test_unresolved_alerts_with_priority_high(self):
        alerts = [
            {"alert_id": "A1", "severity": "WATCH", "priority": "High", "status": "ACTIVE"},
        ]
        summary = build_operational_summary(alerts=alerts)
        assert summary.unresolved_alerts == 1
        assert summary.high_priority_alerts == 1

    def test_in_review_queue_item_count_variants(self):
        q = [
            {"queue_id": "Q1", "status": "IN_REVIEW"},
            {"queue_id": "Q2", "status": "In Review"},
        ]
        summary = build_operational_summary(queue_items=q)
        assert summary.investigations_in_review == 2

    def test_closed_status_mapped_to_resolved_queue(self):
        q = [
            {"queue_id": "Q1", "status": "CLOSED"},
            {"queue_id": "Q2", "status": "Resolved"},
        ]
        summary = build_operational_summary(queue_items=q)
        assert summary.investigations_resolved == 2

    def test_point_analysis_type_mapping(self):
        recs = [
            {"analysis_id": "R1", "analysis_type": "point"},
            {"analysis_id": "R2", "analysis_type": "heat_intelligence"},
        ]
        summary = build_operational_summary(records=recs)
        assert summary.analysis_types["heat_intelligence"] == 2

    def test_missing_data_quality_falls_back_cleanly(self):
        recs = [{"analysis_id": "R1", "metrics": {"mean_temp": 30.0, "total_tiles": 5}}]
        summary = build_operational_summary(records=recs)
        assert sum(summary.data_quality_distribution.values()) == 1

    def test_immutability_of_returned_summary(self):
        summary = build_operational_summary()
        with pytest.raises(Exception):
            summary.completed_analyses = 99  # type: ignore

    def test_has_data_is_true_when_only_signals_exist(self):
        sigs = [{"signal_id": "S1", "severity": "INFO"}]
        summary = build_operational_summary(signals=sigs)
        assert summary.has_data is True

    def test_has_data_is_true_when_only_queue_exists(self):
        q = [{"queue_id": "Q1", "status": "OPEN"}]
        summary = build_operational_summary(queue_items=q)
        assert summary.has_data is True

    def test_suppressed_alerts_ignored_in_unresolved_count(self):
        alerts = [{"alert_id": "A1", "status": "SUPPRESSED"}]
        summary = build_operational_summary(alerts=alerts)
        assert summary.unresolved_alerts == 0

    def test_zero_network_calls(self, monkeypatch):
        import socket
        import httpx

        def _bad_network(*args, **kwargs):
            raise AssertionError("Network prohibited!")

        monkeypatch.setattr(httpx.Client, "send", _bad_network)
        monkeypatch.setattr(socket, "create_connection", _bad_network)

        recs = [MockRecord("R1")]
        summary = build_operational_summary(records=recs)
        assert summary.completed_analyses == 1
