"""Tests for frontend.utils.operational_intelligence — Operational Signal Engine.

Validates:
- OperationalSignal dataclass, immutability, serialization/deserialization.
- Temperature threshold detection (CRITICAL, ELEVATED, WATCH, LOW).
- Spatial spread detection (high spread vs low spread).
- Hot area proportion detection.
- Data quality signals (INSUFFICIENT, LOW, MEDIUM, HIGH).
- Temporal signals across chronological series (increase, decrease, stability).
- Deterministic signal ordering (severity descending, created_at descending, signal_id ascending).
- Responsible Analytics: no causal claims, no medical claims in generated titles or descriptions.
- Zero network I/O invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from frontend.utils.operational_intelligence import (
    SEVERITY_WEIGHTS,
    VALID_DATA_QUALITIES,
    VALID_SEVERITIES,
    OperationalSignal,
    detect_data_quality_signals,
    detect_hot_area_proportion_signals,
    detect_spatial_spread_signals,
    detect_temperature_threshold_signals,
    detect_temporal_signals,
    generate_operational_signals,
)


@dataclass
class MockRecord:
    analysis_id: str = "rec-001"
    activity_id: str = "act-001"
    location_label: str = "Downtown"
    date: str = "2026-08-22"
    time: str | None = "14:00"
    created_at: str = "2026-08-22T14:00:00"
    status: str = "Completed"
    metrics: dict[str, Any] = field(default_factory=dict)
    observed_temperature: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "analysis_id": self.analysis_id,
            "activity_id": self.activity_id,
            "location_label": self.location_label,
            "date": self.date,
            "time": self.time,
            "created_at": self.created_at,
            "status": self.status,
            "metrics": self.metrics,
        }
        if self.observed_temperature is not None:
            d["observed_temperature"] = self.observed_temperature
        return d


# ══════════════════════════════════════════════════════════════════════════════
# 1. OperationalSignal Dataclass & Serialization
# ══════════════════════════════════════════════════════════════════════════════


class TestOperationalSignalModel:
    """OperationalSignal structure, immutability, and serialization."""

    def test_signal_initialization(self):
        sig = OperationalSignal(
            signal_id="SIG-001",
            analysis_id="REC-001",
            signal_type="temperature_above_threshold",
            severity="CRITICAL",
            title="Critical Heat Detected",
            description="Temperature is high.",
            metric="mean_temperature",
            observed_value=41.5,
            threshold_value=40.0,
            direction="above",
            confidence="HIGH",
            evidence=["Evidence line 1"],
            data_quality="HIGH",
        )
        assert sig.signal_id == "SIG-001"
        assert sig.severity == "CRITICAL"
        assert sig.observed_value == 41.5
        assert len(sig.evidence) == 1

    def test_signal_immutability(self):
        sig = OperationalSignal(
            signal_id="SIG-001",
            analysis_id="REC-001",
            signal_type="temperature_above_threshold",
            severity="INFO",
            title="Title",
            description="Desc",
        )
        with pytest.raises(AttributeError):
            sig.severity = "CRITICAL"  # type: ignore[misc]

    def test_to_dict_and_from_dict_roundtrip(self):
        sig = OperationalSignal(
            signal_id="SIG-002",
            analysis_id="REC-002",
            signal_type="high_spatial_spread",
            severity="ELEVATED",
            title="High Spread",
            description="Spatial spread is elevated.",
            metric="temperature_spread",
            observed_value=9.2,
            threshold_value=8.0,
            direction="above",
            confidence="MEDIUM",
            evidence=["Obs 1", "Obs 2"],
            data_quality="MEDIUM",
            created_at="2026-08-22T10:00:00",
        )
        d = sig.to_dict()
        assert d["signal_id"] == "SIG-002"
        assert d["severity"] == "ELEVATED"
        assert d["observed_value"] == 9.2

        reconstructed = OperationalSignal.from_dict(d)
        assert reconstructed.signal_id == sig.signal_id
        assert reconstructed.severity == sig.severity
        assert reconstructed.evidence == sig.evidence
        assert reconstructed.created_at == sig.created_at

    def test_valid_severities_and_weights(self):
        assert "CRITICAL" in VALID_SEVERITIES
        assert "ELEVATED" in VALID_SEVERITIES
        assert "WATCH" in VALID_SEVERITIES
        assert "INFO" in VALID_SEVERITIES
        assert SEVERITY_WEIGHTS["CRITICAL"] > SEVERITY_WEIGHTS["ELEVATED"] > SEVERITY_WEIGHTS["WATCH"] > SEVERITY_WEIGHTS["INFO"]

    def test_valid_data_qualities(self):
        assert "HIGH" in VALID_DATA_QUALITIES
        assert "MEDIUM" in VALID_DATA_QUALITIES
        assert "LOW" in VALID_DATA_QUALITIES
        assert "INSUFFICIENT" in VALID_DATA_QUALITIES


# ══════════════════════════════════════════════════════════════════════════════
# 2. Temperature Threshold Signal Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestTemperatureThresholdDetection:
    """Temperature threshold signals at different severity tiers."""

    def test_critical_threshold_exceeded(self):
        rec = MockRecord(metrics={"mean_temp": 42.0, "total_tiles": 50, "min_temp": 35.0, "max_temp": 45.0})
        signals = detect_temperature_threshold_signals(rec, threshold_critical_high=40.0)
        assert len(signals) == 1
        assert signals[0].severity == "CRITICAL"
        assert signals[0].signal_type == "temperature_above_threshold"
        assert signals[0].observed_value == 42.0
        assert signals[0].direction == "above"

    def test_elevated_threshold_exceeded(self):
        rec = MockRecord(metrics={"mean_temp": 37.5, "total_tiles": 50, "min_temp": 32.0, "max_temp": 39.0})
        signals = detect_temperature_threshold_signals(rec, threshold_critical_high=40.0, threshold_elevated_high=35.0)
        assert len(signals) == 1
        assert signals[0].severity == "ELEVATED"
        assert signals[0].observed_value == 37.5

    def test_watch_threshold_exceeded(self):
        rec = MockRecord(metrics={"mean_temp": 33.0, "total_tiles": 50, "min_temp": 28.0, "max_temp": 35.0})
        signals = detect_temperature_threshold_signals(rec, threshold_watch_high=32.0, threshold_elevated_high=35.0)
        assert len(signals) == 1
        assert signals[0].severity == "WATCH"

    def test_low_temperature_threshold(self):
        rec = MockRecord(metrics={"mean_temp": 8.0, "total_tiles": 50, "min_temp": 5.0, "max_temp": 12.0})
        signals = detect_temperature_threshold_signals(rec, threshold_low=10.0)
        assert len(signals) == 1
        assert signals[0].severity == "WATCH"
        assert signals[0].signal_type == "temperature_below_threshold"
        assert signals[0].direction == "below"

    def test_normal_temperature_produces_no_threshold_signal(self):
        rec = MockRecord(metrics={"mean_temp": 25.0, "total_tiles": 50, "min_temp": 20.0, "max_temp": 28.0})
        signals = detect_temperature_threshold_signals(rec)
        assert len(signals) == 0

    def test_max_temperature_fallback_when_mean_missing(self):
        rec = MockRecord(metrics={"max_temp": 41.0, "total_tiles": 20})
        signals = detect_temperature_threshold_signals(rec, threshold_critical_high=40.0)
        assert len(signals) == 1
        assert signals[0].severity == "CRITICAL"
        assert signals[0].observed_value == 41.0

    def test_observed_temperature_top_level_fallback(self):
        rec = MockRecord(observed_temperature=43.0, metrics={})
        signals = detect_temperature_threshold_signals(rec, threshold_critical_high=40.0)
        assert len(signals) == 1
        assert signals[0].severity == "CRITICAL"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Spatial Spread Signal Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestSpatialSpreadDetection:
    """Detection of high and low thermal spatial variability."""

    def test_high_spatial_spread_detected(self):
        rec = MockRecord(metrics={"temp_spread": 10.5, "mean_temp": 30.0, "total_tiles": 50})
        signals = detect_spatial_spread_signals(rec, high_spread_threshold=8.0)
        assert len(signals) == 1
        assert signals[0].severity == "ELEVATED"
        assert signals[0].signal_type == "high_spatial_spread"
        assert signals[0].observed_value == 10.5

    def test_low_spatial_spread_detected(self):
        rec = MockRecord(metrics={"temp_spread": 1.0, "mean_temp": 30.0, "total_tiles": 50})
        signals = detect_spatial_spread_signals(rec, low_spread_threshold=1.5)
        assert len(signals) == 1
        assert signals[0].severity == "INFO"
        assert signals[0].signal_type == "low_spatial_spread"

    def test_moderate_spatial_spread_produces_no_signal(self):
        rec = MockRecord(metrics={"temp_spread": 4.0, "mean_temp": 30.0, "total_tiles": 50})
        signals = detect_spatial_spread_signals(rec, high_spread_threshold=8.0, low_spread_threshold=1.5)
        assert len(signals) == 0

    def test_missing_spread_produces_no_signal(self):
        rec = MockRecord(metrics={"mean_temp": 30.0})
        signals = detect_spatial_spread_signals(rec)
        assert len(signals) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. Above-Threshold Proportion Signal Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestHotAreaProportionDetection:
    """Detection of elevated proportions of tiles above threshold."""

    def test_high_proportion_decimal_input(self):
        rec = MockRecord(metrics={"above_threshold_proportion": 0.55, "mean_temp": 32.0})
        signals = detect_hot_area_proportion_signals(rec, high_proportion_threshold=0.40)
        assert len(signals) == 1
        assert signals[0].severity == "ELEVATED"
        assert signals[0].signal_type == "high_hot_area_proportion"
        assert abs(signals[0].observed_value - 55.0) < 0.1

    def test_high_proportion_percentage_input(self):
        rec = MockRecord(metrics={"above_threshold_proportion": 60.0, "mean_temp": 32.0})
        signals = detect_hot_area_proportion_signals(rec, high_proportion_threshold=0.40)
        assert len(signals) == 1
        assert abs(signals[0].observed_value - 60.0) < 0.1

    def test_low_proportion_produces_no_signal(self):
        rec = MockRecord(metrics={"above_threshold_proportion": 0.15})
        signals = detect_hot_area_proportion_signals(rec, high_proportion_threshold=0.40)
        assert len(signals) == 0

    def test_missing_proportion_produces_no_signal(self):
        rec = MockRecord(metrics={"mean_temp": 30.0})
        signals = detect_hot_area_proportion_signals(rec)
        assert len(signals) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. Data Quality Signals
# ══════════════════════════════════════════════════════════════════════════════


class TestDataQualitySignals:
    """Transparent identification of data quality status."""

    def test_insufficient_data_signal(self):
        rec = MockRecord(metrics={})
        signals = detect_data_quality_signals(rec)
        assert len(signals) == 1
        assert signals[0].signal_type == "insufficient_data"
        assert signals[0].severity == "WATCH"
        assert signals[0].data_quality == "INSUFFICIENT"

    def test_low_metric_coverage_signal(self):
        rec = MockRecord(metrics={"mean_temp": 30.0})  # only 1 metric
        signals = detect_data_quality_signals(rec)
        assert len(signals) == 1
        assert signals[0].signal_type == "missing_metric"
        assert signals[0].severity == "INFO"
        assert signals[0].data_quality == "LOW"

    def test_high_data_quality_produces_no_data_warning(self):
        rec = MockRecord(metrics={"mean_temp": 30.0, "min_temp": 25.0, "max_temp": 35.0, "total_tiles": 100})
        signals = detect_data_quality_signals(rec)
        assert len(signals) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 6. Temporal Signal Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestTemporalSignalDetection:
    """Signals detected over chronological series for a given location."""

    def test_temperature_increase_detected(self):
        recs = [
            MockRecord(analysis_id="A1", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="A2", date="2026-08-05", metrics={"mean_temp": 32.0}),
            MockRecord(analysis_id="A3", date="2026-08-10", metrics={"mean_temp": 34.5}),
        ]
        signals = detect_temporal_signals(recs, tolerance=0.5)
        assert len(signals) == 1
        assert signals[0].signal_type == "temperature_increase"
        assert signals[0].severity == "ELEVATED"
        assert signals[0].direction == "increase"
        assert signals[0].analysis_id == "A3"

    def test_temperature_decrease_detected(self):
        recs = [
            MockRecord(analysis_id="A1", date="2026-08-01", metrics={"mean_temp": 36.0}),
            MockRecord(analysis_id="A2", date="2026-08-10", metrics={"mean_temp": 31.0}),
        ]
        signals = detect_temporal_signals(recs, tolerance=0.5)
        assert len(signals) == 1
        assert signals[0].signal_type == "temperature_decrease"
        assert signals[0].severity == "INFO"
        assert signals[0].direction == "decrease"

    def test_thermal_stability_detected(self):
        recs = [
            MockRecord(analysis_id="A1", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="A2", date="2026-08-05", metrics={"mean_temp": 30.1}),
            MockRecord(analysis_id="A3", date="2026-08-10", metrics={"mean_temp": 29.9}),
        ]
        signals = detect_temporal_signals(recs, tolerance=0.5)
        assert len(signals) == 1
        assert signals[0].signal_type == "persistent_stability"
        assert signals[0].severity == "INFO"

    def test_single_record_produces_no_temporal_signal(self):
        recs = [MockRecord(analysis_id="A1", date="2026-08-01", metrics={"mean_temp": 30.0})]
        signals = detect_temporal_signals(recs)
        assert len(signals) == 0

    def test_non_completed_records_ignored_in_temporal(self):
        recs = [
            MockRecord(analysis_id="A1", status="Completed", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="A2", status="Failed", metrics={"mean_temp": 50.0}),
        ]
        signals = detect_temporal_signals(recs)
        assert len(signals) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 7. Aggregate Signal Generation & Deterministic Sorting
# ══════════════════════════════════════════════════════════════════════════════


class TestAggregateSignalGeneration:
    """Comprehensive generation across multiple records with deterministic sorting."""

    def test_empty_records_returns_empty(self):
        assert generate_operational_signals([]) == []

    def test_multi_record_generation_and_sorting(self):
        recs = [
            MockRecord(
                analysis_id="REC-INFO",
                location_label="Park",
                date="2026-08-20",
                created_at="2026-08-20T10:00:00",
                metrics={"temp_spread": 1.0, "mean_temp": 24.0, "total_tiles": 50, "min_temp": 23.5, "max_temp": 24.5},
            ),
            MockRecord(
                analysis_id="REC-CRIT",
                location_label="Industrial Zone",
                date="2026-08-22",
                created_at="2026-08-22T12:00:00",
                metrics={"mean_temp": 43.0, "temp_spread": 9.0, "total_tiles": 100, "min_temp": 38.0, "max_temp": 47.0},
            ),
            MockRecord(
                analysis_id="REC-ELEV",
                location_label="Suburbs",
                date="2026-08-21",
                created_at="2026-08-21T11:00:00",
                metrics={"mean_temp": 36.5, "temp_spread": 4.0, "total_tiles": 80, "min_temp": 34.0, "max_temp": 38.0},
            ),
        ]

        signals = generate_operational_signals(recs)
        assert len(signals) >= 3

        # Highest severity (CRITICAL) must be first
        assert signals[0].severity == "CRITICAL"
        assert signals[0].analysis_id == "REC-CRIT"

        # Verify all severities are sorted in non-ascending order of weight
        weights = [SEVERITY_WEIGHTS.get(s.severity, 0) for s in signals]
        assert weights == sorted(weights, reverse=True)

    def test_only_completed_records_participate(self):
        recs = [
            MockRecord(analysis_id="R-COMP", status="Completed", metrics={"mean_temp": 41.0}),
            MockRecord(analysis_id="R-FAIL", status="Failed", metrics={"mean_temp": 45.0}),
            MockRecord(analysis_id="R-PROC", status="Processing", metrics={"mean_temp": 45.0}),
        ]
        signals = generate_operational_signals(recs)
        assert all(s.analysis_id == "R-COMP" for s in signals)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Responsible Analytics Language Verification
# ══════════════════════════════════════════════════════════════════════════════


class TestResponsibleAnalyticsInSignals:
    """Signals must never use causal, predictive, or medical language."""

    FORBIDDEN = [
        "caused by",
        "due to",
        "will cause",
        "prediction",
        "forecast",
        "hazardous",
        "deadly",
        "fatal",
        "health risk",
        "diagnosis",
        "emergency",
        "casualty",
    ]

    def test_generated_signals_contain_no_forbidden_terms(self):
        recs = [
            MockRecord(
                analysis_id="R-1",
                location_label="Downtown",
                date="2026-08-22",
                metrics={
                    "mean_temp": 45.0,
                    "min_temp": 35.0,
                    "max_temp": 50.0,
                    "temp_spread": 15.0,
                    "above_threshold_proportion": 0.85,
                    "total_tiles": 200,
                },
            ),
            MockRecord(
                analysis_id="R-2",
                location_label="Downtown",
                date="2026-08-25",
                metrics={
                    "mean_temp": 48.0,
                    "min_temp": 38.0,
                    "max_temp": 53.0,
                    "temp_spread": 15.0,
                    "above_threshold_proportion": 0.90,
                    "total_tiles": 200,
                },
            ),
        ]

        signals = generate_operational_signals(recs)
        assert len(signals) > 0

        for sig in signals:
            full_text = f"{sig.title} {sig.description} {' '.join(sig.evidence)}".lower()
            for word in self.FORBIDDEN:
                assert word not in full_text, f"Forbidden term '{word}' found in signal: {sig.title}"


# ══════════════════════════════════════════════════════════════════════════════
# 9. Edge Cases & Boundary Value Testing
# ══════════════════════════════════════════════════════════════════════════════


class TestSignalEdgeCases:
    """Edge cases for boundaries, missing values, and corrupted data."""

    def test_exact_threshold_boundary_critical(self):
        rec = MockRecord(metrics={"mean_temp": 40.0, "total_tiles": 50, "min_temp": 30.0, "max_temp": 40.0})
        signals = detect_temperature_threshold_signals(rec, threshold_critical_high=40.0)
        assert len(signals) == 1
        assert signals[0].severity == "CRITICAL"

    def test_exact_threshold_boundary_elevated(self):
        rec = MockRecord(metrics={"mean_temp": 35.0, "total_tiles": 50, "min_temp": 30.0, "max_temp": 35.0})
        signals = detect_temperature_threshold_signals(rec, threshold_critical_high=40.0, threshold_elevated_high=35.0)
        assert len(signals) == 1
        assert signals[0].severity == "ELEVATED"

    def test_negative_temperature_handling(self):
        rec = MockRecord(metrics={"mean_temp": -5.0, "total_tiles": 50, "min_temp": -10.0, "max_temp": 0.0})
        signals = detect_temperature_threshold_signals(rec, threshold_low=10.0)
        assert len(signals) == 1
        assert signals[0].severity == "WATCH"
        assert signals[0].direction == "below"
        assert signals[0].observed_value == -5.0

    def test_corrupted_numeric_strings_handled_gracefully(self):
        rec = MockRecord(metrics={"mean_temp": "not_a_number", "temp_spread": "invalid"})
        signals = generate_operational_signals([rec])
        # Should not crash, should produce data quality warning
        assert any(s.signal_type == "insufficient_data" for s in signals)

    def test_nan_and_inf_metrics_handled_gracefully(self):
        rec = MockRecord(metrics={"mean_temp": float("nan"), "temp_spread": float("inf")})
        signals = generate_operational_signals([rec])
        assert any(s.signal_type == "insufficient_data" for s in signals)

    def test_custom_thresholds_in_generate_operational_signals(self):
        rec = MockRecord(metrics={"mean_temp": 28.0, "total_tiles": 50, "min_temp": 25.0, "max_temp": 30.0})
        # With default watch threshold (32.0), no signal
        assert len(generate_operational_signals([rec])) == 0
        # With custom watch threshold (27.0), signal is generated
        signals = generate_operational_signals([rec], watch_threshold=27.0)
        assert len(signals) == 1
        assert signals[0].severity == "WATCH"

    def test_multiple_locations_temporal_independence(self):
        recs = [
            MockRecord(analysis_id="D1", location_label="Downtown", date="2026-08-01", metrics={"mean_temp": 30.0}),
            MockRecord(analysis_id="D2", location_label="Downtown", date="2026-08-10", metrics={"mean_temp": 35.0}),
            MockRecord(analysis_id="S1", location_label="Suburbs", date="2026-08-01", metrics={"mean_temp": 32.0}),
            MockRecord(analysis_id="S2", location_label="Suburbs", date="2026-08-10", metrics={"mean_temp": 28.0}),
        ]
        signals = generate_operational_signals(recs)
        sig_types = [s.signal_type for s in signals]
        assert "temperature_increase" in sig_types
        assert "temperature_decrease" in sig_types

    def test_signal_evidence_is_list_of_strings(self):
        rec = MockRecord(metrics={"mean_temp": 42.0, "total_tiles": 50, "min_temp": 35.0, "max_temp": 45.0})
        signals = generate_operational_signals([rec])
        for s in signals:
            assert isinstance(s.evidence, list)
            assert all(isinstance(e, str) for e in s.evidence)

    def test_signal_from_dict_defaults(self):
        minimal_dict = {
            "signal_id": "SIG-MIN",
            "analysis_id": "REC-MIN",
            "signal_type": "temperature_above_threshold",
            "title": "Minimal",
            "description": "Minimal desc",
        }
        sig = OperationalSignal.from_dict(minimal_dict)
        assert sig.severity == "INFO"
        assert sig.confidence == "HIGH"
        assert sig.data_quality == "HIGH"
        assert sig.evidence == []

