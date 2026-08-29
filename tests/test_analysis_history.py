"""Comprehensive unit test suite for AnalysisRecord and session-local Analysis Workspace history."""

from __future__ import annotations

import streamlit as st

from frontend.utils.analysis_history import (
    MAX_HISTORY_RECORDS,
    MAX_PINNED_RECORDS,
    MAX_TAGS_PER_RECORD,
    AnalysisRecord,
    add_analysis_record,
    add_tag_to_analysis_record,
    clear_all_analysis_records,
    delete_analysis_record,
    generate_analysis_id,
    get_analysis_record,
    get_analysis_record_by_activity_id,
    list_analysis_records,
    pin_analysis_record,
    remove_tag_from_analysis_record,
    sanitize_value_for_history,
    search_and_filter_records,
    unpin_analysis_record,
)


def setup_function() -> None:
    """Clear session state before each test."""
    clear_all_analysis_records()


# ──────────────────────────────────────────────────────────────────────────────
# Creation & ID Generation Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_generate_analysis_id_format() -> None:
    """Analysis IDs must follow HI/HM-YYYYMMDD-### deterministic format."""
    id_hi = generate_analysis_id("heat_intelligence")
    id_hm = generate_analysis_id("heatmap")

    assert id_hi.startswith("HI-")
    assert id_hm.startswith("HM-")
    assert len(id_hi.split("-")) == 3
    assert len(id_hm.split("-")) == 3


def test_create_and_retrieve_heat_intelligence_record() -> None:
    """Creates a valid Heat Intelligence record and verifies retrieval."""
    rec = AnalysisRecord(
        analysis_id="",
        activity_id="act_hi_123",
        analysis_type="heat_intelligence",
        created_at="2026-08-22 14:00:00",
        updated_at="2026-08-22 14:00:00",
        location_label="Downtown Point",
        latitude=40.7128,
        longitude=-74.0060,
        date="2026-08-22",
        observed_temperature=33.5,
        categories=["urban", "geographic"],
        status="Completed",
        summary="Report Ready (PDF)",
    )
    saved = add_analysis_record(rec)

    assert saved.analysis_id.startswith("HI-")
    fetched = get_analysis_record(saved.analysis_id)
    assert fetched is not None
    assert fetched.activity_id == "act_hi_123"
    assert fetched.latitude == 40.7128
    assert fetched.observed_temperature == 33.5
    assert fetched.categories == ["urban", "geographic"]


def test_create_and_retrieve_heatmap_record() -> None:
    """Creates a valid Heatmap record and verifies retrieval by activity ID."""
    rec = AnalysisRecord(
        analysis_id="",
        activity_id="act_hm_456",
        analysis_type="heatmap",
        created_at="2026-08-22 14:30:00",
        updated_at="2026-08-22 14:30:00",
        location_label="Lower Manhattan AOI",
        date="2026-08-22",
        time="14:00",
        granularity=100,
        metrics={"mean_temp": 31.4, "total_tiles": 84, "temp_spread": 4.2},
        status="Completed",
    )
    saved = add_analysis_record(rec)

    assert saved.analysis_id.startswith("HM-")
    fetched = get_analysis_record_by_activity_id("act_hm_456")
    assert fetched is not None
    assert fetched.metrics["mean_temp"] == 31.4
    assert fetched.granularity == 100


def test_get_nonexistent_analysis_returns_none() -> None:
    """Looking up a missing analysis ID returns None safely."""
    assert get_analysis_record("HI-99999999-999") is None
    assert get_analysis_record("") is None
    assert get_analysis_record_by_activity_id("nonexistent") is None


# ──────────────────────────────────────────────────────────────────────────────
# Capacity & Pruning Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_capacity_trimming_removes_oldest_unpinned_first() -> None:
    """Adding 51st record removes the oldest unpinned record and preserves pinned."""
    # Add 50 records, pin the first (oldest) one
    for i in range(50):
        rec = AnalysisRecord(
            analysis_id=f"TEST-{i:03d}",
            activity_id=f"act_{i}",
            analysis_type="heatmap",
            created_at=f"2026-08-22 10:{i:02d}:00",
            updated_at=f"2026-08-22 10:{i:02d}:00",
            location_label=f"Loc {i}",
            pinned=(i == 0),  # Pin the oldest item
        )
        add_analysis_record(rec)

    records = list_analysis_records()
    assert len(records) == 50

    # Add the 51st record
    rec_51 = AnalysisRecord(
        analysis_id="TEST-051",
        activity_id="act_51",
        analysis_type="heatmap",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Loc 51",
    )
    add_analysis_record(rec_51)

    updated = list_analysis_records()
    assert len(updated) == 50

    # Pinned oldest record (TEST-000) must still exist
    assert get_analysis_record("TEST-000") is not None
    # Oldest unpinned record (TEST-001) should have been trimmed
    assert get_analysis_record("TEST-001") is None
    # Newest record (TEST-051) must exist
    assert get_analysis_record("TEST-051") is not None


# ──────────────────────────────────────────────────────────────────────────────
# Pinning Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_pin_and_unpin_analysis() -> None:
    """Tests pinning and unpinning an analysis record."""
    rec = AnalysisRecord(
        analysis_id="TEST-PIN-01",
        activity_id="act_pin_1",
        analysis_type="heatmap",
        created_at="2026-08-22 12:00:00",
        updated_at="2026-08-22 12:00:00",
        location_label="Pin Test",
    )
    add_analysis_record(rec)

    ok, err = pin_analysis_record("TEST-PIN-01")
    assert ok is True
    assert err is None
    assert get_analysis_record("TEST-PIN-01").pinned is True

    unpin_ok = unpin_analysis_record("TEST-PIN-01")
    assert unpin_ok is True
    assert get_analysis_record("TEST-PIN-01").pinned is False


def test_pinning_limit_max_10() -> None:
    """Attempting to pin an 11th analysis record returns a user-facing error."""
    # Create 11 records and pin first 10
    for i in range(11):
        rec = AnalysisRecord(
            analysis_id=f"PIN-TEST-{i}",
            activity_id=f"act_p_{i}",
            analysis_type="heatmap",
            created_at=f"2026-08-22 12:{i:02d}:00",
            updated_at=f"2026-08-22 12:{i:02d}:00",
            location_label=f"Pin Loc {i}",
        )
        add_analysis_record(rec)
        if i < 10:
            ok, err = pin_analysis_record(f"PIN-TEST-{i}")
            assert ok is True

    # 11th pin attempt
    ok, err = pin_analysis_record("PIN-TEST-10")
    assert ok is False
    assert "Maximum of 10 pinned" in err
    assert get_analysis_record("PIN-TEST-10").pinned is False


# ──────────────────────────────────────────────────────────────────────────────
# Tagging Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_tag_normalization_and_deduplication() -> None:
    """Tags are normalized to lowercase, trimmed, deduplicated, and length-capped."""
    rec = AnalysisRecord(
        analysis_id="TEST-TAG-01",
        activity_id="act_tag_1",
        analysis_type="heatmap",
        created_at="2026-08-22 12:00:00",
        updated_at="2026-08-22 12:00:00",
        location_label="Tag Test",
    )
    add_analysis_record(rec)

    # Add tag with whitespace and uppercase
    ok, err = add_tag_to_analysis_record("TEST-TAG-01", "  Downtown Urban  ")
    assert ok is True
    fetched = get_analysis_record("TEST-TAG-01")
    assert fetched.tags == ["downtown urban"]

    # Duplicate tag
    ok2, _ = add_tag_to_analysis_record("TEST-TAG-01", "downtown urban")
    assert ok2 is True
    assert get_analysis_record("TEST-TAG-01").tags == ["downtown urban"]

    # Remove tag
    rm_ok = remove_tag_from_analysis_record("TEST-TAG-01", "downtown urban")
    assert rm_ok is True
    assert get_analysis_record("TEST-TAG-01").tags == []


def test_tagging_capacity_limit_max_10() -> None:
    """Cannot exceed 10 tags per analysis record."""
    rec = AnalysisRecord(
        analysis_id="TEST-TAG-LIMIT",
        activity_id="act_tag_lim",
        analysis_type="heatmap",
        created_at="2026-08-22 12:00:00",
        updated_at="2026-08-22 12:00:00",
        location_label="Tag Limit Test",
    )
    add_analysis_record(rec)

    for i in range(10):
        ok, _ = add_tag_to_analysis_record("TEST-TAG-LIMIT", f"tag_{i}")
        assert ok is True

    # 11th tag attempt
    ok11, err11 = add_tag_to_analysis_record("TEST-TAG-LIMIT", "tag_11")
    assert ok11 is False
    assert "Maximum of 10 tags" in err11


# ──────────────────────────────────────────────────────────────────────────────
# Search, Filter & Sort Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_search_by_id_location_tag_category() -> None:
    """Tests multi-field case-insensitive search."""
    r1 = AnalysisRecord(
        analysis_id="HI-20260822-001",
        activity_id="act_1",
        analysis_type="heat_intelligence",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Financial District",
        categories=["urban", "anthropogenic"],
        tags=["baseline", "summer"],
    )
    r2 = AnalysisRecord(
        analysis_id="HM-20260822-002",
        activity_id="act_2",
        analysis_type="heatmap",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Central Park",
        tags=["park", "vegetation"],
    )
    add_analysis_record(r1)
    add_analysis_record(r2)

    # Search by ID
    res_id = search_and_filter_records(query="HI-20260822-001")
    assert len(res_id) == 1
    assert res_id[0].analysis_id == "HI-20260822-001"

    # Search by Location substring
    res_loc = search_and_filter_records(query="financial")
    assert len(res_loc) == 1
    assert res_loc[0].location_label == "Financial District"

    # Search by Tag
    res_tag = search_and_filter_records(query="summer")
    assert len(res_tag) == 1
    assert res_tag[0].analysis_id == "HI-20260822-001"

    # Search by Category
    res_cat = search_and_filter_records(query="anthropogenic")
    assert len(res_cat) == 1
    assert res_cat[0].analysis_id == "HI-20260822-001"


def test_filter_by_type_status_and_pinned() -> None:
    """Filters records by analysis type, status, and pinned status."""
    r1 = AnalysisRecord(
        analysis_id="R1",
        activity_id="a1",
        analysis_type="heat_intelligence",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Loc 1",
        status="Completed",
        pinned=True,
    )
    r2 = AnalysisRecord(
        analysis_id="R2",
        activity_id="a2",
        analysis_type="heatmap",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Loc 2",
        status="Processing",
        pinned=False,
    )
    add_analysis_record(r1)
    add_analysis_record(r2)

    # Filter by type
    only_hm = search_and_filter_records(type_filter="heatmap")
    assert len(only_hm) == 1
    assert only_hm[0].analysis_id == "R2"

    # Filter by status
    only_proc = search_and_filter_records(status_filter="Processing")
    assert len(only_proc) == 1
    assert only_proc[0].analysis_id == "R2"

    # Filter by pinned
    only_pinned = search_and_filter_records(pinned_only=True)
    assert len(only_pinned) == 1
    assert only_pinned[0].analysis_id == "R1"


def test_deterministic_sorting() -> None:
    """Sorts records deterministically by Newest, Oldest, Pinned First, and Location A–Z."""
    r1 = AnalysisRecord(
        analysis_id="A",
        activity_id="act_a",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Zebra District",
        pinned=False,
    )
    r2 = AnalysisRecord(
        analysis_id="B",
        activity_id="act_b",
        analysis_type="heatmap",
        created_at="2026-08-22 12:00:00",
        updated_at="2026-08-22 12:00:00",
        location_label="Apple Park",
        pinned=True,
    )
    add_analysis_record(r1)
    add_analysis_record(r2)

    newest = search_and_filter_records(sort_by="Newest")
    assert [r.analysis_id for r in newest] == ["B", "A"]

    oldest = search_and_filter_records(sort_by="Oldest")
    assert [r.analysis_id for r in oldest] == ["A", "B"]

    pinned_first = search_and_filter_records(sort_by="Pinned First")
    assert [r.analysis_id for r in pinned_first] == ["B", "A"]

    loc_az = search_and_filter_records(sort_by="Location A–Z")
    assert [r.analysis_id for r in loc_az] == ["B", "A"]


# ──────────────────────────────────────────────────────────────────────────────
# Delete & Clear Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_delete_analysis_record() -> None:
    """Deleting a record removes only that record and resets active detail state if matching."""
    r1 = AnalysisRecord(
        analysis_id="DEL-1",
        activity_id="a_del_1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Delete Me",
    )
    r2 = AnalysisRecord(
        analysis_id="KEEP-2",
        activity_id="a_keep_2",
        analysis_type="heatmap",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Keep Me",
    )
    add_analysis_record(r1)
    add_analysis_record(r2)

    st.session_state["_active_detail_analysis_id"] = "DEL-1"

    deleted = delete_analysis_record("DEL-1")
    assert deleted is True
    assert get_analysis_record("DEL-1") is None
    assert get_analysis_record("KEEP-2") is not None
    assert st.session_state.get("_active_detail_analysis_id") is None


def test_delete_nonexistent_returns_false() -> None:
    """Attempting to delete a nonexistent analysis ID returns False."""
    assert delete_analysis_record("NONEXISTENT") is False


def test_clear_all_records() -> None:
    """Clearing all records empties the workspace completely."""
    r1 = AnalysisRecord(
        analysis_id="C1",
        activity_id="act_c1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Clear 1",
    )
    add_analysis_record(r1)
    assert len(list_analysis_records()) == 1

    clear_all_analysis_records()
    assert len(list_analysis_records()) == 0


# ──────────────────────────────────────────────────────────────────────────────
# Security & Sanitization Audit
# ──────────────────────────────────────────────────────────────────────────────


def test_record_sanitization_never_stores_secrets() -> None:
    """Verifies that API keys, tokens, signed URLs, and credentials are wiped before storage."""
    raw_payload = {
        "api_key": "fg-secret-12345",
        "token": "bearer-xyz",
        "Authorization": "Bearer 123",
        "download_link": "https://s3.amazonaws.com/bucket/report.pdf?X-Amz-Signature=secret123",
        "safe_metric": 42.5,
        "nested": {
            "credentials": "admin:pass",
            "safe_location": "Midtown",
            "signed_url": "https://s3.signed.url",
        },
    }

    cleaned = sanitize_value_for_history(raw_payload)

    assert "api_key" not in cleaned
    assert "token" not in cleaned
    assert "Authorization" not in cleaned
    assert "download_link" not in cleaned
    assert cleaned["safe_metric"] == 42.5
    assert "credentials" not in cleaned["nested"]
    assert "signed_url" not in cleaned["nested"]
    assert cleaned["nested"]["safe_location"] == "Midtown"


def test_analysis_record_roundtrip_dict() -> None:
    """Serializing to dict and deserializing from dict preserves all fields."""
    rec = AnalysisRecord(
        analysis_id="HI-20260822-099",
        activity_id="act_roundtrip",
        analysis_type="heat_intelligence",
        created_at="2026-08-22 15:00:00",
        updated_at="2026-08-22 15:00:00",
        location_label="Roundtrip Test",
        latitude=40.7128,
        longitude=-74.0060,
        date="2026-08-22",
        observed_temperature=30.0,
        categories=["urban", "geographic"],
        metrics={"score": 95},
        tags=["roundtrip"],
        pinned=True,
    )
    d = rec.to_dict()
    restored = AnalysisRecord.from_dict(d)

    assert restored.analysis_id == rec.analysis_id
    assert restored.activity_id == rec.activity_id
    assert restored.latitude == rec.latitude
    assert restored.pinned is True
    assert restored.tags == ["roundtrip"]


def test_filter_by_date_ranges() -> None:
    """Filters records by date (Today, Last 7 Days, All)."""
    from datetime import date as dt_date, timedelta
    today_str = dt_date.today().strftime("%Y-%m-%d")
    yesterday_str = (dt_date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    old_date_str = (dt_date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

    r_today = AnalysisRecord(
        analysis_id="R-TODAY",
        activity_id="act_today",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Today Loc",
        date=today_str,
    )
    r_yesterday = AnalysisRecord(
        analysis_id="R-YESTERDAY",
        activity_id="act_yesterday",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Yesterday Loc",
        date=yesterday_str,
    )
    r_old = AnalysisRecord(
        analysis_id="R-OLD",
        activity_id="act_old",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Old Loc",
        date=old_date_str,
    )
    add_analysis_record(r_today)
    add_analysis_record(r_yesterday)
    add_analysis_record(r_old)

    # Filter Today
    today_res = search_and_filter_records(date_filter="Today")
    assert len(today_res) == 1
    assert today_res[0].analysis_id == "R-TODAY"

    # Filter Last 7 Days
    last_7_res = search_and_filter_records(date_filter="Last 7 Days")
    assert len(last_7_res) == 2
    assert {r.analysis_id for r in last_7_res} == {"R-TODAY", "R-YESTERDAY"}

    # Filter All
    all_res = search_and_filter_records(date_filter="All")
    assert len(all_res) == 3


def test_tag_edge_cases_and_rejections() -> None:
    """Rejects empty, whitespace-only tags and handles nonexistent analyses."""
    rec = AnalysisRecord(
        analysis_id="TEST-TAG-EDGES",
        activity_id="act_tag_edges",
        analysis_type="heatmap",
        created_at="2026-08-22 12:00:00",
        updated_at="2026-08-22 12:00:00",
        location_label="Tag Edges",
    )
    add_analysis_record(rec)

    # Whitespace only
    ok1, err1 = add_tag_to_analysis_record("TEST-TAG-EDGES", "   ")
    assert ok1 is False
    assert "Invalid tag" in err1

    # Nonexistent record
    ok2, err2 = add_tag_to_analysis_record("NONEXISTENT", "validtag")
    assert ok2 is False
    assert "not found" in err2

    # Remove nonexistent tag from record returns False
    rm_res = remove_tag_from_analysis_record("TEST-TAG-EDGES", "not_there")
    assert rm_res is False


def test_pin_edge_cases() -> None:
    """Pinning nonexistent record returns error; unpinning unpinned record returns False."""
    ok, err = pin_analysis_record("NONEXISTENT")
    assert ok is False
    assert "not found" in err

    unpin_res = unpin_analysis_record("NONEXISTENT")
    assert unpin_res is False


def test_generate_analysis_id_counter_increments_per_type() -> None:
    """Counters increment monotonically for each analysis type."""
    id1 = generate_analysis_id("heat_intelligence")
    id2 = generate_analysis_id("heat_intelligence")
    id_hm = generate_analysis_id("heatmap")

    num1 = int(id1.split("-")[-1])
    num2 = int(id2.split("-")[-1])
    assert num2 == num1 + 1
    assert id_hm.startswith("HM-")


def test_trimming_when_all_records_are_unpinned() -> None:
    """When all 50 records are unpinned, adding 51st trims oldest at the end of list."""
    for i in range(50):
        add_analysis_record(AnalysisRecord(
            analysis_id=f"UNPIN-{i:03d}",
            activity_id=f"act_unpin_{i}",
            analysis_type="heatmap",
            created_at=f"2026-08-22 08:{i:02d}:00",
            updated_at=f"2026-08-22 08:{i:02d}:00",
            location_label=f"Loc {i}",
        ))

    add_analysis_record(AnalysisRecord(
        analysis_id="UNPIN-051",
        activity_id="act_unpin_51",
        analysis_type="heatmap",
        created_at="2026-08-22 09:00:00",
        updated_at="2026-08-22 09:00:00",
        location_label="Loc 51",
    ))

    recs = list_analysis_records()
    assert len(recs) == 50
    # Oldest record UNPIN-000 should be pruned
    assert get_analysis_record("UNPIN-000") is None
    # Newest record UNPIN-051 must exist
    assert get_analysis_record("UNPIN-051") is not None


def test_update_existing_record_preserves_id() -> None:
    """Updating an existing record mutates its fields without creating a duplicate record."""
    r = add_analysis_record(AnalysisRecord(
        analysis_id="UPDATE-001",
        activity_id="act_up_1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Initial Label",
        status="Processing",
    ))

    # Update status to Completed
    r.status = "Completed"
    r.location_label = "Updated Label"
    add_analysis_record(r)

    recs = list_analysis_records()
    assert len(recs) == 1
    assert recs[0].status == "Completed"
    assert recs[0].location_label == "Updated Label"


def test_search_empty_query_returns_all_records() -> None:
    """Empty search query returns all active records."""
    add_analysis_record(AnalysisRecord(
        analysis_id="Q1",
        activity_id="act_q1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Query Loc 1",
    ))
    add_analysis_record(AnalysisRecord(
        analysis_id="Q2",
        activity_id="act_q2",
        analysis_type="heat_intelligence",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Query Loc 2",
    ))

    res = search_and_filter_records(query="   ")
    assert len(res) == 2


def test_filter_by_status_all_returns_all() -> None:
    """Filtering by status='All' does not drop records of any status."""
    add_analysis_record(AnalysisRecord(
        analysis_id="S1",
        activity_id="act_s1",
        analysis_type="heatmap",
        created_at="2026-08-22 10:00:00",
        updated_at="2026-08-22 10:00:00",
        location_label="Status 1",
        status="Completed",
    ))
    add_analysis_record(AnalysisRecord(
        analysis_id="S2",
        activity_id="act_s2",
        analysis_type="heatmap",
        created_at="2026-08-22 11:00:00",
        updated_at="2026-08-22 11:00:00",
        location_label="Status 2",
        status="Processing",
    ))

    res = search_and_filter_records(status_filter="All")
    assert len(res) == 2



