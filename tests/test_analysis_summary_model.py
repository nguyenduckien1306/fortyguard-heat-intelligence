"""Tests for the normalized AnalysisSummary metadata model."""

from __future__ import annotations

from backend.models.summary import AnalysisSummary, extract_analysis_summary


def test_analysis_summary_model_instantiation() -> None:
    summary = AnalysisSummary(
        analysis_type="heatmap",
        activity_id="act-summary-001",
        status="Completed",
        label="Downtown Manhattan",
        summary_metrics={"tile_count": 150, "mean_temperature": 32.4},
        has_report_download=False,
    )
    assert summary.analysis_type == "heatmap"
    assert summary.activity_id == "act-summary-001"
    assert summary.status == "Completed"
    assert summary.summary_metrics["tile_count"] == 150
    assert not summary.has_report_download


def test_extract_analysis_summary_heatmap() -> None:
    heatmap_result = {
        "map_data": {
            "type": "FeatureCollection",
            "features": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
        },
        "stats_data": {
            "temperature_stats": {
                "mean": 28.5,
                "min": 24.1,
                "max": 33.2,
            }
        },
    }
    summary = extract_analysis_summary(
        "heatmap",
        "act-hm-100",
        "Completed",
        result=heatmap_result,
        request_payload={"granularity": 100},
        label="Test AOI",
    )
    assert summary.analysis_type == "heatmap"
    assert summary.activity_id == "act-hm-100"
    assert summary.status == "Completed"
    assert summary.label == "Test AOI"
    assert summary.summary_metrics["tile_count"] == 3
    assert summary.summary_metrics["mean_temperature"] == 28.5
    assert summary.summary_metrics["min_temperature"] == 24.1
    assert summary.summary_metrics["max_temperature"] == 33.2
    assert summary.summary_metrics["granularity"] == 100
    assert not summary.has_report_download


def test_extract_analysis_summary_heat_intelligence() -> None:
    hi_result = {
        "download_link": "https://example.invalid/report.pdf",
    }
    summary = extract_analysis_summary(
        "heat_intelligence",
        "act-hi-200",
        "Completed",
        result=hi_result,
        request_payload={
            "latitude": 40.7050,
            "longitude": -74.0090,
            "temperature": 32.5,
            "date": "2024-07-15",
            "analysis": ["environmental", "urban"],
        },
    )
    assert summary.analysis_type == "heat_intelligence"
    assert summary.activity_id == "act-hi-200"
    assert summary.status == "Completed"
    assert summary.has_report_download is True
    assert summary.summary_metrics["observed_temperature"] == 32.5
    assert summary.summary_metrics["analysis_dimensions"] == ["environmental", "urban"]


def test_extract_analysis_summary_handles_none_gracefully() -> None:
    summary = extract_analysis_summary(
        "heatmap",
        "act-none-001",
        "Processing",
        result=None,
        request_payload=None,
    )
    assert summary.status == "Processing"
    assert summary.summary_metrics == {}
    assert summary.has_report_download is False
