"""Canonical Intelligence Snapshot Data Structure.

Captures a complete, deterministic, and immutable snapshot of all evaluated intelligence:
- Source AnalysisRecord IDs
- Watchlist Evaluations
- Operational Signals & Dispositions
- Promoted & Suppressed Alerts
- Investigation Queue Items
- Priority & Data Quality Summaries
- System Observability & Diagnostics

Strict Invariants:
1. Zero HTTP / Network I/O.
2. Identical inputs evaluated with the same clock produce the same canonical snapshot.
3. Schema versioned for backward/forward session compatibility.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock

SCHEMA_VERSION: int = 1


@dataclass(frozen=True)
class IntelligenceSnapshot:
    """Immutable, canonical snapshot of a complete intelligence evaluation cycle."""

    snapshot_id: str
    generated_at: str
    record_ids: list[str]
    watchlist_evaluations: list[dict[str, Any]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    queue_items: list[dict[str, Any]] = field(default_factory=list)
    priority_summary: dict[str, int] = field(default_factory=lambda: {"Critical": 0, "High": 0, "Medium": 0, "Low": 0})
    data_quality_summary: dict[str, int] = field(default_factory=lambda: {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INSUFFICIENT": 0})
    diagnostics_summary: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> IntelligenceSnapshot:
        return cls(
            snapshot_id=str(data.get("snapshot_id", "")),
            generated_at=str(data.get("generated_at", "")),
            record_ids=list(data.get("record_ids", [])),
            watchlist_evaluations=list(data.get("watchlist_evaluations", [])),
            signals=list(data.get("signals", [])),
            alerts=list(data.get("alerts", [])),
            queue_items=list(data.get("queue_items", [])),
            priority_summary=dict(data.get("priority_summary", {"Critical": 0, "High": 0, "Medium": 0, "Low": 0})),
            data_quality_summary=dict(data.get("data_quality_summary", {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "INSUFFICIENT": 0})),
            diagnostics_summary=dict(data.get("diagnostics_summary", {})),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )

    def canonical_hash(self) -> str:
        """Compute a deterministic SHA-256 fingerprint of the snapshot contents."""
        content = {
            "record_ids": sorted(self.record_ids),
            "watchlist_evaluations": sorted(
                [e.get("eval_id", "") or str(e.get("watchlist_id", "")) for e in self.watchlist_evaluations]
            ),
            "signals": sorted([s.get("signal_id", "") for s in self.signals]),
            "alerts": sorted([a.get("alert_id", "") for a in self.alerts]),
            "priority_summary": self.priority_summary,
            "data_quality_summary": self.data_quality_summary,
            "schema_version": self.schema_version,
        }
        canonical_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


IntelligenceSnapshot.to_dict = IntelligenceSnapshot.to_dict
IntelligenceSnapshot.canonical_hash = IntelligenceSnapshot.canonical_hash
IntelligenceSnapshot.to_dict = IntelligenceSnapshot.to_dict
IntelligenceSnapshot.canonical_hash = IntelligenceSnapshot.canonical_hash
