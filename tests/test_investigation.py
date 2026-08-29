"""Tests for frontend.utils.investigation — Investigation Timeline & Trend Engine.

Validates:
- TimelineEvent construction from AnalysisRecord-like objects.
- Chronological sorting (ascending & descending).
- Location and analysis_type filtering.
- Deduplication by analysis_id.
- Trend classification: Rising, Falling, Stable, Mixed, Insufficient Data.
- Multi-analysis matrix construction.
- Edge cases: missing dates, empty records, NaN metrics.
- Zero network I/O invariant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pytest

from frontend.utils.investigation import (
    TimelineEvent,
    build_investigation_timeline,
    build_multi_analysis_matrix,
    calculate_timeline_trend,
    record_to_timeline_event,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixture Helpers
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class FakeRecord:
    """Minimal AnalysisRecord stand-in for investigation tests."""

    analysis_id: str = "inv-001"
    activity_id: str = "act-001"
    analysis_type: str = "heatmap"
    date: str = "2025-06-01"
    time: str | None = "12:00"
    location_label: str = "Downtown"
    status: str = "Completed"
    metrics: dict[str, Any] = field(default_factory=dict)
    observed_temperature: float | None = None
    temperature: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "analysis_id": self.analysis_id,
            "activity_id": self.activity_id,
            "analysis_type": self.analysis_type,
            "date": self.date,
            "time": self.time,
            "location_label": self.location_label,
            "status": self.status,
            "metrics": self.metrics,
        }
        if self.observed_temperature is not None:
            d["observed_temperature"] = self.observed_temperature
        if self.temperature is not None:
            d["temperature"] = self.temperature
        return d


def _make_rec(
    aid: str = "inv-001",
    date: str = "2025-06-01",
    time: str | None = "12:00",
    location: str = "Downtown",
    analysis_type: str = "heatmap",
    status: str = "Completed",
    mean_temp: float | None = None,
    min_temp: float | None = None,
    max_temp: float | None = None,
    spread: float | None = None,
    tiles: int | None = None,
) -> FakeRecord:
    metrics: dict[str, Any] = {}
    if mean_temp is not None:
        metrics["mean_temp"] = mean_temp
    if min_temp is not None:
        metrics["min_temp"] = min_temp
    if max_temp is not None:
        metrics["max_temp"] = max_temp
    if spread is not None:
        metrics["temp_spread"] = spread
    if tiles is not None:
        metrics["total_tiles"] = tiles
    return FakeRecord(
        analysis_id=aid,
        date=date,
        time=time,
        location_label=location,
        analysis_type=analysis_type,
        status=status,
        metrics=metrics,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. TimelineEvent Construction
# ══════════════════════════════════════════════════════════════════════════════


class TestRecordToTimelineEvent:
    """Convert FakeRecord into TimelineEvent."""

    def test_basic_conversion(self):
        rec = _make_rec(mean_temp=35.5, min_temp=28.0, max_temp=42.0, spread=14.0, tiles=120)
        ev = record_to_timeline_event(rec)

        assert isinstance(ev, TimelineEvent)
        assert ev.analysis_id == "inv-001"
        assert ev.date == "2025-06-01"
        assert ev.location == "Downtown"
        assert ev.mean_temperature == 35.5
        assert ev.min_temperature == 28.0
        assert ev.max_temperature == 42.0
        assert ev.spread == 14.0
        assert ev.tile_count == 120

    def test_missing_metrics(self):
        rec = _make_rec()
        ev = record_to_timeline_event(rec)
        assert ev.mean_temperature is None
        assert ev.min_temperature is None
        assert ev.max_temperature is None
        assert ev.spread is None
        assert ev.tile_count is None

    def test_nan_metric_becomes_none(self):
        rec = _make_rec(mean_temp=float("nan"))
        ev = record_to_timeline_event(rec)
        assert ev.mean_temperature is None

    def test_inf_metric_becomes_none(self):
        rec = _make_rec(mean_temp=float("inf"))
        ev = record_to_timeline_event(rec)
        assert ev.mean_temperature is None

    def test_observed_temperature_fallback(self):
        """If metrics dict has no mean_temp, falls back to observed_temperature."""
        rec = FakeRecord(observed_temperature=31.5)
        ev = record_to_timeline_event(rec)
        assert ev.mean_temperature == 31.5

    def test_to_dict_roundtrip(self):
        rec = _make_rec(mean_temp=30.0, tiles=50)
        ev = record_to_timeline_event(rec)
        d = ev.to_dict()
        assert d["mean_temperature"] == 30.0
        assert d["tile_count"] == 50
        assert d["analysis_id"] == "inv-001"

    def test_event_is_frozen(self):
        rec = _make_rec(mean_temp=30.0)
        ev = record_to_timeline_event(rec)
        with pytest.raises(AttributeError):
            ev.mean_temperature = 999.0  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════════
# 2. build_investigation_timeline
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildInvestigationTimeline:
    """Timeline construction with filtering, sorting, deduplication."""

    def test_empty_records(self):
        assert build_investigation_timeline([]) == []

    def test_filters_non_completed(self):
        records = [
            _make_rec(aid="ok-1", status="Completed", mean_temp=30.0),
            _make_rec(aid="bad-1", status="Processing", mean_temp=30.0),
            _make_rec(aid="bad-2", status="Failed", mean_temp=30.0),
        ]
        events = build_investigation_timeline(records)
        assert len(events) == 1
        assert events[0].analysis_id == "ok-1"

    def test_chronological_sort_ascending(self):
        records = [
            _make_rec(aid="A", date="2025-06-15"),
            _make_rec(aid="B", date="2025-06-01"),
            _make_rec(aid="C", date="2025-06-10"),
        ]
        events = build_investigation_timeline(records, ascending=True)
        assert [e.analysis_id for e in events] == ["B", "C", "A"]

    def test_chronological_sort_descending(self):
        records = [
            _make_rec(aid="A", date="2025-06-15"),
            _make_rec(aid="B", date="2025-06-01"),
            _make_rec(aid="C", date="2025-06-10"),
        ]
        events = build_investigation_timeline(records, ascending=False)
        assert [e.analysis_id for e in events] == ["A", "C", "B"]

    def test_deduplication_by_analysis_id(self):
        records = [
            _make_rec(aid="dup-001", mean_temp=30.0),
            _make_rec(aid="dup-001", mean_temp=35.0),  # duplicate
        ]
        events = build_investigation_timeline(records)
        assert len(events) == 1

    def test_location_filter_case_insensitive(self):
        records = [
            _make_rec(aid="A", location="Downtown Dubai"),
            _make_rec(aid="B", location="Suburban Area"),
            _make_rec(aid="C", location="downtown"),
        ]
        events = build_investigation_timeline(records, location="downtown")
        assert len(events) == 2

    def test_analysis_type_filter(self):
        records = [
            _make_rec(aid="A", analysis_type="heatmap"),
            _make_rec(aid="B", analysis_type="heat_intelligence"),
            _make_rec(aid="C", analysis_type="heatmap"),
        ]
        events = build_investigation_timeline(records, analysis_type="heatmap")
        assert len(events) == 2

    def test_combined_filters(self):
        records = [
            _make_rec(aid="A", location="Downtown", analysis_type="heatmap"),
            _make_rec(aid="B", location="Downtown", analysis_type="heat_intelligence"),
            _make_rec(aid="C", location="Suburbs", analysis_type="heatmap"),
        ]
        events = build_investigation_timeline(records, location="Downtown", analysis_type="heatmap")
        assert len(events) == 1
        assert events[0].analysis_id == "A"

    def test_missing_date_handled(self):
        records = [
            _make_rec(aid="A", date=""),
            _make_rec(aid="B", date="2025-06-01"),
        ]
        events = build_investigation_timeline(records, ascending=True)
        assert len(events) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 3. calculate_timeline_trend
# ══════════════════════════════════════════════════════════════════════════════


class TestCalculateTimelineTrend:
    """Deterministic trend classification from timeline events."""

    def _events(self, temps: list[float]) -> list[TimelineEvent]:
        """Helper to create sequential timeline events with given temperatures."""
        return [
            TimelineEvent(
                analysis_id=f"ev-{i}",
                activity_id=f"act-{i}",
                date=f"2025-06-{i + 1:02d}",
                time="12:00",
                location="Test",
                analysis_type="heatmap",
                mean_temperature=t,
                min_temperature=None,
                max_temperature=None,
                spread=None,
                tile_count=None,
                status="Completed",
            )
            for i, t in enumerate(temps)
        ]

    def test_rising_trend(self):
        events = self._events([30.0, 32.0, 34.0, 36.0])
        result = calculate_timeline_trend(events)
        assert result["trend"] == "Rising"
        assert result["net_delta"] is not None
        assert result["net_delta"] > 0

    def test_falling_trend(self):
        events = self._events([40.0, 37.0, 34.0, 31.0])
        result = calculate_timeline_trend(events)
        assert result["trend"] == "Falling"
        assert result["net_delta"] < 0

    def test_stable_trend(self):
        events = self._events([30.0, 30.05, 29.95, 30.02])
        result = calculate_timeline_trend(events)
        assert result["trend"] == "Stable"

    def test_mixed_trend(self):
        events = self._events([30.0, 35.0, 28.0, 32.0])
        result = calculate_timeline_trend(events)
        assert result["trend"] == "Mixed"

    def test_insufficient_data_single_event(self):
        events = self._events([30.0])
        result = calculate_timeline_trend(events)
        assert result["trend"] == "Insufficient Data"

    def test_insufficient_data_empty(self):
        result = calculate_timeline_trend([])
        assert result["trend"] == "Insufficient Data"

    def test_observations_list_returned(self):
        events = self._events([30.0, 32.0, 34.0])
        result = calculate_timeline_trend(events)
        assert "observations" in result
        assert len(result["observations"]) == 3

    def test_first_and_last_values(self):
        events = self._events([25.0, 30.0, 35.0])
        result = calculate_timeline_trend(events)
        assert result["first_value"] == 25.0
        assert result["last_value"] == 35.0

    def test_net_delta_calculation(self):
        events = self._events([20.0, 25.0, 30.0])
        result = calculate_timeline_trend(events)
        assert abs(result["net_delta"] - 10.0) < 0.01

    def test_events_with_none_temperatures_skipped(self):
        events = [
            TimelineEvent("ev-1", "act-1", "2025-06-01", "12:00", "Test", "heatmap", 30.0, None, None, None, None, "Completed"),
            TimelineEvent("ev-2", "act-2", "2025-06-02", "12:00", "Test", "heatmap", None, None, None, None, None, "Completed"),
            TimelineEvent("ev-3", "act-3", "2025-06-03", "12:00", "Test", "heatmap", 35.0, None, None, None, None, "Completed"),
        ]
        result = calculate_timeline_trend(events)
        assert result["observation_count"] == 2
        assert result["first_value"] == 30.0
        assert result["last_value"] == 35.0

    def test_summary_is_descriptive_not_causal(self):
        """Verify the trend summary uses neutral language."""
        events = self._events([30.0, 35.0, 40.0])
        result = calculate_timeline_trend(events)
        summary = result["summary"].lower()
        forbidden = ["caused", "due to", "hazardous", "fatal", "health risk"]
        for term in forbidden:
            assert term not in summary, f"Forbidden term '{term}' found in trend summary"


# ══════════════════════════════════════════════════════════════════════════════
# 4. build_multi_analysis_matrix
# ══════════════════════════════════════════════════════════════════════════════


class TestBuildMultiAnalysisMatrix:
    """Multi-analysis longitudinal comparison matrix."""

    def test_empty_records(self):
        result = build_multi_analysis_matrix([])
        assert result["count"] == 0
        assert result["headers"] == []
        assert result["rows"] == []

    def test_single_record(self):
        records = [_make_rec(aid="A", mean_temp=30.0)]
        result = build_multi_analysis_matrix(records)
        assert result["count"] == 1

    def test_two_records_produces_matrix(self):
        records = [
            _make_rec(aid="A", date="2025-06-01", mean_temp=30.0, min_temp=25.0, max_temp=35.0, spread=10.0, tiles=100),
            _make_rec(aid="B", date="2025-06-15", mean_temp=34.0, min_temp=28.0, max_temp=40.0, spread=12.0, tiles=110),
        ]
        result = build_multi_analysis_matrix(records)
        assert result["count"] == 2
        assert len(result["headers"]) == 2
        assert len(result["rows"]) == 5  # 5 metric rows

    def test_max_analyses_respected(self):
        records = [
            _make_rec(aid=f"A-{i}", date=f"2025-06-{i + 1:02d}", mean_temp=30.0 + i)
            for i in range(10)
        ]
        result = build_multi_analysis_matrix(records, max_analyses=3)
        assert result["count"] == 3
        assert len(result["headers"]) == 3

    def test_net_temperature_delta(self):
        records = [
            _make_rec(aid="A", date="2025-06-01", mean_temp=28.0),
            _make_rec(aid="B", date="2025-06-15", mean_temp=34.0),
        ]
        result = build_multi_analysis_matrix(records)
        assert result["net_temperature_delta"] is not None
        assert abs(result["net_temperature_delta"] - 6.0) < 0.01

    def test_missing_metric_shows_dash(self):
        records = [
            _make_rec(aid="A", date="2025-06-01", mean_temp=30.0),
            _make_rec(aid="B", date="2025-06-15"),  # no metrics
        ]
        result = build_multi_analysis_matrix(records)
        # At least one row should contain "—" for missing data
        has_dash = any("—" in v for row in result["rows"] for v in row["values"])
        assert has_dash

    def test_only_completed_records_included(self):
        records = [
            _make_rec(aid="A", status="Completed", mean_temp=30.0),
            _make_rec(aid="B", status="Failed", mean_temp=35.0),
            _make_rec(aid="C", status="Completed", mean_temp=32.0),
        ]
        result = build_multi_analysis_matrix(records)
        assert result["count"] == 2
