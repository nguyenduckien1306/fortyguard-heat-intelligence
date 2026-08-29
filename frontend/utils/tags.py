"""Session-local analysis tagging and pinning.

Provides lightweight, session-scoped tagging and pinning for analyses
without introducing databases, authentication, persistence, or additional
security surfaces.

Tags are user-local UI metadata stored in Streamlit session state.
They are treated as plain text — no HTML execution, no secret storage.
"""

from __future__ import annotations

from typing import Any
import streamlit as st


_PINS_KEY = "_session_pinned_analyses"
_TAGS_KEY = "_session_analysis_tags"
_MAX_PINNED = 10
_MAX_TAGS_PER_ANALYSIS = 10
_MAX_TAG_LENGTH = 30
_MIN_TAG_LENGTH = 1


# ──────────────────────────────────────────────────────────────────────────────
# Tag normalization
# ──────────────────────────────────────────────────────────────────────────────


def normalize_analysis_tag(tag: str) -> str | None:
    """Normalize a tag string for storage.

    - Strips leading/trailing whitespace.
    - Converts to lowercase.
    - Truncates to MAX_TAG_LENGTH characters.
    - Rejects empty, whitespace-only, or too-short results.

    Returns the normalized tag or None if invalid.
    """
    if not isinstance(tag, str):
        return None

    cleaned = tag.strip().lower()

    if len(cleaned) < _MIN_TAG_LENGTH:
        return None

    # Truncate to max length
    cleaned = cleaned[:_MAX_TAG_LENGTH]

    return cleaned


# ──────────────────────────────────────────────────────────────────────────────
# Tag storage
# ──────────────────────────────────────────────────────────────────────────────


def _get_tags_store() -> dict[str, list[str]]:
    """Get or initialize the tags session store."""
    if _TAGS_KEY not in st.session_state:
        st.session_state[_TAGS_KEY] = {}
    return st.session_state[_TAGS_KEY]


def get_analysis_tags(activity_id: str) -> list[str]:
    """Retrieve the list of tags for a given analysis."""
    if not activity_id:
        return []
    store = _get_tags_store()
    return list(store.get(activity_id, []))


def set_analysis_tags(activity_id: str, tags: list[str]) -> list[str]:
    """Set the tags for an analysis, normalizing and deduplicating.

    Returns the final list of accepted tags.
    """
    if not activity_id:
        return []

    store = _get_tags_store()
    normalized: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        norm = normalize_analysis_tag(tag)
        if norm and norm not in seen and len(normalized) < _MAX_TAGS_PER_ANALYSIS:
            normalized.append(norm)
            seen.add(norm)

    store[activity_id] = normalized
    st.session_state[_TAGS_KEY] = store
    return normalized


def add_analysis_tag(activity_id: str, tag: str) -> list[str]:
    """Add a single tag to an analysis. Returns updated tag list."""
    if not activity_id:
        return []

    current = get_analysis_tags(activity_id)
    norm = normalize_analysis_tag(tag)

    if not norm:
        return current

    if norm in current:
        return current  # Already exists

    if len(current) >= _MAX_TAGS_PER_ANALYSIS:
        return current  # At capacity

    current.append(norm)
    store = _get_tags_store()
    store[activity_id] = current
    st.session_state[_TAGS_KEY] = store
    return current


def remove_analysis_tag(activity_id: str, tag: str) -> list[str]:
    """Remove a specific tag from an analysis. Returns updated tag list."""
    if not activity_id:
        return []

    norm = normalize_analysis_tag(tag)
    if not norm:
        return get_analysis_tags(activity_id)

    current = get_analysis_tags(activity_id)
    current = [t for t in current if t != norm]

    store = _get_tags_store()
    store[activity_id] = current
    st.session_state[_TAGS_KEY] = store
    return current


def get_all_tagged_analyses() -> dict[str, list[str]]:
    """Return a mapping of activity_id → tags for all tagged analyses."""
    return dict(_get_tags_store())


# ──────────────────────────────────────────────────────────────────────────────
# Pinning
# ──────────────────────────────────────────────────────────────────────────────


def _get_pins_store() -> list[str]:
    """Get or initialize the pins session store."""
    if _PINS_KEY not in st.session_state:
        st.session_state[_PINS_KEY] = []
    return st.session_state[_PINS_KEY]


def pin_analysis(activity_id: str) -> bool:
    """Pin an analysis for quick access.

    Returns True if the pin was added, False if already pinned or at capacity.
    """
    if not activity_id:
        return False

    pins = _get_pins_store()

    if activity_id in pins:
        return False  # Already pinned

    if len(pins) >= _MAX_PINNED:
        return False  # At capacity

    pins.append(activity_id)
    st.session_state[_PINS_KEY] = pins
    return True


def unpin_analysis(activity_id: str) -> bool:
    """Unpin an analysis.

    Returns True if the pin was removed, False if not pinned.
    """
    if not activity_id:
        return False

    pins = _get_pins_store()

    if activity_id not in pins:
        return False

    pins.remove(activity_id)
    st.session_state[_PINS_KEY] = pins
    return True


def is_analysis_pinned(activity_id: str) -> bool:
    """Check if an analysis is currently pinned."""
    if not activity_id:
        return False
    return activity_id in _get_pins_store()


def get_pinned_analyses() -> list[str]:
    """Return list of pinned activity IDs."""
    return list(_get_pins_store())


def clear_pins() -> None:
    """Clear all pins."""
    st.session_state[_PINS_KEY] = []


def clear_tags() -> None:
    """Clear all tags."""
    st.session_state[_TAGS_KEY] = {}
