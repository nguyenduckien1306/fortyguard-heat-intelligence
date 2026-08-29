"""Tests for session-local analysis tagging and pinning utilities."""

from __future__ import annotations

from frontend.utils.tags import (
    add_analysis_tag,
    clear_pins,
    clear_tags,
    get_all_tagged_analyses,
    get_analysis_tags,
    get_pinned_analyses,
    is_analysis_pinned,
    normalize_analysis_tag,
    pin_analysis,
    remove_analysis_tag,
    set_analysis_tags,
    unpin_analysis,
)


# ──────────────────────────────────────────────────────────────────────────────
# Tag normalization
# ──────────────────────────────────────────────────────────────────────────────


def test_normalize_tag_basic() -> None:
    assert normalize_analysis_tag("  Hot Day  ") == "hot day"


def test_normalize_tag_case() -> None:
    assert normalize_analysis_tag("BASELINE") == "baseline"


def test_normalize_tag_truncation() -> None:
    long_tag = "a" * 50
    result = normalize_analysis_tag(long_tag)
    assert result is not None
    assert len(result) == 30


def test_normalize_tag_empty() -> None:
    assert normalize_analysis_tag("") is None
    assert normalize_analysis_tag("   ") is None


def test_normalize_tag_non_string() -> None:
    assert normalize_analysis_tag(123) is None  # type: ignore
    assert normalize_analysis_tag(None) is None  # type: ignore


def test_normalize_tag_special_characters() -> None:
    result = normalize_analysis_tag("hot-day #1")
    assert result == "hot-day #1"


def test_normalize_tag_secret_like_string() -> None:
    # Should normalize but not execute — tags are plain text
    result = normalize_analysis_tag("<script>alert('xss')</script>")
    assert result is not None
    assert result == "<script>alert('xss')</script>"[:30]


# ──────────────────────────────────────────────────────────────────────────────
# Tag operations
# ──────────────────────────────────────────────────────────────────────────────


def test_set_and_get_tags() -> None:
    clear_tags()
    result = set_analysis_tags("act-t1", ["hot day", "baseline", "review"])
    assert result == ["hot day", "baseline", "review"]
    assert get_analysis_tags("act-t1") == ["hot day", "baseline", "review"]


def test_set_tags_deduplicates() -> None:
    clear_tags()
    result = set_analysis_tags("act-t2", ["hot", "HOT", "hot"])
    assert result == ["hot"]


def test_set_tags_limits_count() -> None:
    clear_tags()
    tags = [f"tag{i}" for i in range(15)]
    result = set_analysis_tags("act-t3", tags)
    assert len(result) == 10  # Max 10


def test_set_tags_empty_activity_id() -> None:
    clear_tags()
    assert set_analysis_tags("", ["tag"]) == []


def test_add_tag() -> None:
    clear_tags()
    set_analysis_tags("act-t4", ["existing"])
    result = add_analysis_tag("act-t4", "new")
    assert "existing" in result
    assert "new" in result


def test_add_tag_duplicate() -> None:
    clear_tags()
    set_analysis_tags("act-t5", ["existing"])
    result = add_analysis_tag("act-t5", "EXISTING")
    assert len(result) == 1


def test_remove_tag() -> None:
    clear_tags()
    set_analysis_tags("act-t6", ["keep", "remove"])
    result = remove_analysis_tag("act-t6", "remove")
    assert result == ["keep"]


def test_get_tags_missing_id() -> None:
    clear_tags()
    assert get_analysis_tags("nonexistent") == []
    assert get_analysis_tags("") == []


def test_get_all_tagged() -> None:
    clear_tags()
    set_analysis_tags("act-a", ["tag1"])
    set_analysis_tags("act-b", ["tag2"])
    all_tags = get_all_tagged_analyses()
    assert "act-a" in all_tags
    assert "act-b" in all_tags


# ──────────────────────────────────────────────────────────────────────────────
# Pinning operations
# ──────────────────────────────────────────────────────────────────────────────


def test_pin_and_unpin() -> None:
    clear_pins()
    assert pin_analysis("act-p1") is True
    assert is_analysis_pinned("act-p1") is True
    assert unpin_analysis("act-p1") is True
    assert is_analysis_pinned("act-p1") is False


def test_pin_duplicate() -> None:
    clear_pins()
    assert pin_analysis("act-p2") is True
    assert pin_analysis("act-p2") is False  # Already pinned


def test_pin_limit() -> None:
    clear_pins()
    for i in range(10):
        assert pin_analysis(f"act-limit-{i}") is True
    # 11th should fail
    assert pin_analysis("act-limit-10") is False


def test_pin_empty_id() -> None:
    clear_pins()
    assert pin_analysis("") is False
    assert is_analysis_pinned("") is False
    assert unpin_analysis("") is False


def test_unpin_not_pinned() -> None:
    clear_pins()
    assert unpin_analysis("never-pinned") is False


def test_get_pinned() -> None:
    clear_pins()
    pin_analysis("act-gp-1")
    pin_analysis("act-gp-2")
    pinned = get_pinned_analyses()
    assert "act-gp-1" in pinned
    assert "act-gp-2" in pinned
    assert len(pinned) == 2
