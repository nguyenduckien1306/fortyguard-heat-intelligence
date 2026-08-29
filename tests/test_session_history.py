"""Tests for frontend session-local analysis history."""

from __future__ import annotations

import streamlit as st
from frontend.utils.history import (
    clear_session_history,
    get_session_history,
    record_session_analysis,
    update_session_analysis_status,
)


def test_session_history_initializes_empty() -> None:
    clear_session_history()
    history = get_session_history()
    assert history == []


def test_record_session_analysis_records_entry() -> None:
    clear_session_history()
    record_session_analysis(
        "Heatmap",
        "act-test-001",
        "Manhattan AOI",
        "Processing",
        "2024-07-15 @ 14:00",
    )
    history = get_session_history()
    assert len(history) == 1
    assert history[0]["activity_id"] == "act-test-001"
    assert history[0]["analysis_type"] == "Heatmap"
    assert history[0]["status"] == "Processing"
    assert history[0]["label"] == "Manhattan AOI"


def test_update_session_analysis_status() -> None:
    clear_session_history()
    record_session_analysis(
        "Heat Intelligence",
        "act-test-002",
        "40.7050, -74.0090",
        "Processing",
    )
    update_session_analysis_status("act-test-002", "Completed", summary="Report Ready (PDF)")
    history = get_session_history()
    assert len(history) == 1
    assert history[0]["status"] == "Completed"
    assert history[0]["summary"] == "Report Ready (PDF)"


def test_session_history_security_never_stores_secrets_or_signed_urls() -> None:
    clear_session_history()
    details_with_sensitive_info = {
        "latitude": 40.7050,
        "download_link": "https://tos-dashboard-prod.s3.amazonaws.com/secret-signed-url",
        "api_key": "secret-key-123",
        "headers": {"api-key": "secret"},
        "token": "bearer-token",
    }
    record_session_analysis(
        "Heat Intelligence",
        "act-test-sec",
        "Location",
        "Completed",
        details=details_with_sensitive_info,
    )
    history = get_session_history()
    entry_details = history[0]["details"]

    assert "download_link" not in entry_details
    assert "api_key" not in entry_details
    assert "headers" not in entry_details
    assert "token" not in entry_details
    assert entry_details["latitude"] == 40.7050


def test_session_history_capping() -> None:
    clear_session_history()
    for i in range(25):
        record_session_analysis("Heatmap", f"act-{i}", f"Label {i}", "Completed")

    history = get_session_history()
    assert len(history) == 20
    assert history[0]["activity_id"] == "act-24"
