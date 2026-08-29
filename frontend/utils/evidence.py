"""Canonical Evidence Bundle and "Why am I seeing this?" Engine.

Constructs explainable, tamper-evident EvidenceBundle structures with SHA-256
evidence hashes, freshness verification, and strictly non-causal narratives.

Strict Invariants:
1. Zero Network / HTTP I/O.
2. Every EvidenceBundle carries a deterministic SHA-256 evidence_hash.
3. Freshness verification compares evidence_as_of against underlying record timestamps.
4. "Why am I seeing this?" provides 100% transparent, evidence-backed explanations.
5. Strictly non-causal, non-predictive, non-medical language.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping, Sequence

from frontend.utils.clock import Clock, get_current_clock, parse_timestamp_safe
from frontend.utils.operational_intelligence import (
    OperationalSignal,
    _determine_record_data_quality,
    _extract_metric_val,
    _safe_float,
)
from frontend.utils.responsible_analytics import RESPONSIBLE_ANALYTICS_NOTICE


@dataclass(frozen=True)
class EvidenceBundle:
    """Immutable, tamper-evident bundle of verified facts backing an alert/signal."""

    evidence_id: str
    target_id: str  # signal_id or alert_id
    analysis_id: str
    evidence_as_of: str
    items: tuple[dict[str, Any], ...]
    why_am_i_seeing_this: str
    data_quality: str = "HIGH"  # HIGH | MEDIUM | LOW | INSUFFICIENT
    limitations: tuple[str, ...] = ()
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["items"] = list(self.items)
        d["limitations"] = list(self.limitations)
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceBundle:
        raw_items = data.get("items", [])
        raw_lims = data.get("limitations", [])
        return cls(
            evidence_id=str(data.get("evidence_id", "")),
            target_id=str(data.get("target_id", "")),
            analysis_id=str(data.get("analysis_id", "")),
            evidence_as_of=str(data.get("evidence_as_of", "")),
            items=tuple(dict(i) for i in raw_items if isinstance(i, Mapping)),
            why_am_i_seeing_this=str(data.get("why_am_i_seeing_this", "")),
            data_quality=str(data.get("data_quality", "HIGH")),
            limitations=tuple(str(l) for l in raw_lims),
            evidence_hash=str(data.get("evidence_hash", "")),
        )


def calculate_evidence_hash(target_id: str, analysis_id: str, items: Sequence[Mapping[str, Any]]) -> str:
    """Compute deterministic SHA-256 hash over canonical evidence items."""
    clean_items = [dict(i) for i in items]
    raw_payload = {
        "target_id": str(target_id).strip(),
        "analysis_id": str(analysis_id).strip(),
        "items": sorted(clean_items, key=lambda x: str(x.get("metric", ""))),
    }
    canonical_str = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def generate_why_seeing_this_narrative(
    target_id: str,
    title: str,
    analysis_id: str,
    evidence_items: Sequence[str | Mapping[str, Any]],
    data_quality: str = "HIGH",
) -> str:
    """Construct a plain-language, non-causal explanation of why an alert/signal fired."""
    lines: list[str] = [
        f"This intelligence notification was triggered for analysis **{analysis_id}**.",
        "",
        "**Triggering Facts:**",
    ]

    if not evidence_items:
        lines.append("- Observed metric values crossed defined monitoring thresholds.")
    else:
        for ev in evidence_items:
            if isinstance(ev, str):
                lines.append(f"- {ev}")
            elif isinstance(ev, Mapping):
                metric = str(ev.get("metric", "Metric"))
                obs = ev.get("observed_value")
                th = ev.get("threshold_value")
                op = str(ev.get("operator", "exceeded"))
                lines.append(f"- {metric}: observed {obs} {op} threshold {th}.")

    lines.append("")
    lines.append(f"**Data Quality Status:** {data_quality.upper()}.")
    return "\n".join(lines)


def build_evidence_bundle(
    target: Any,
    analysis_record: Any | None = None,
    baseline_record: Any | None = None,
    clock: Clock | None = None,
) -> EvidenceBundle:
    """Build a complete EvidenceBundle with SHA-256 hash and freshness timestamp."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    target_dict = target.to_dict() if hasattr(target, "to_dict") else dict(target)
    target_id = str(target_dict.get("alert_id") or target_dict.get("signal_id") or target_dict.get("queue_id") or "UNKNOWN")
    analysis_id = str(target_dict.get("analysis_id", ""))
    title = str(target_dict.get("title") or target_dict.get("reason") or target_dict.get("policy_name") or "Operational Event")
    raw_evidence = target_dict.get("evidence", [])
    dq = str(target_dict.get("data_quality") or "HIGH")

    items_list: list[dict[str, Any]] = []

    # If raw evidence strings or dicts exist, convert to structured items
    if isinstance(raw_evidence, Sequence) and raw_evidence:
        for idx, ev in enumerate(raw_evidence):
            if isinstance(ev, str):
                items_list.append({
                    "item_id": f"EV-ITEM-{idx:02d}",
                    "metric": target_dict.get("metric", "mean_temperature"),
                    "observed_value": target_dict.get("observed_value"),
                    "threshold_value": target_dict.get("threshold_value"),
                    "evidence_text": ev,
                    "is_stale": False,
                })
            elif isinstance(ev, Mapping):
                d = dict(ev)
                d["is_stale"] = False
                if target_dict.get("observed_value") is not None and d.get("observed_value") is None:
                    d["observed_value"] = target_dict.get("observed_value")
                if target_dict.get("threshold_value") is not None and d.get("threshold_value") is None:
                    d["threshold_value"] = target_dict.get("threshold_value")
                if target_dict.get("metric") is not None and not d.get("metric"):
                    d["metric"] = target_dict.get("metric")
                items_list.append(d)
    elif target_dict.get("observed_value") is not None or target_dict.get("threshold_value") is not None:
        metric_name = target_dict.get("metric") or "mean_temperature"
        obs_val = target_dict.get("observed_value")
        th_val = target_dict.get("threshold_value")
        ev_text = f"Observed {metric_name} is {obs_val} (Threshold: {th_val})." if th_val is not None else f"Observed {metric_name} is {obs_val}."
        items_list.append({
            "item_id": "EV-ITEM-01",
            "metric": metric_name,
            "observed_value": obs_val,
            "threshold_value": th_val,
            "evidence_text": ev_text,
            "is_stale": False,
        })
    elif not items_list and analysis_record:
        rec_dict = analysis_record.to_dict() if hasattr(analysis_record, "to_dict") else dict(analysis_record)
        mean_t = _extract_metric_val(rec_dict, ["mean_temp", "mean_temperature", "observed_temperature", "temperature"])
        spread_t = _extract_metric_val(rec_dict, ["temp_spread", "temperature_spread"])
        if mean_t is not None:
            items_list.append({
                "item_id": "EV-ITEM-01",
                "metric": "observed_temperature" if (rec_dict.get("observed_temperature") is not None and not (isinstance(rec_dict.get("metrics"), Mapping) and rec_dict["metrics"].get("mean_temp"))) else "mean_temperature",
                "observed_value": mean_t,
                "threshold_value": target_dict.get("threshold_value"),
                "evidence_text": f"Observed temperature is {mean_t:.2f}°C.",
                "is_stale": False,
            })
        if spread_t is not None:
            items_list.append({
                "item_id": "EV-ITEM-02",
                "metric": "temperature_spread",
                "observed_value": spread_t,
                "threshold_value": None,
                "evidence_text": f"Observed temperature spread is {spread_t:.2f}°C.",
                "is_stale": False,
            })

    narrative = generate_why_seeing_this_narrative(
        target_id=target_id,
        title=title,
        analysis_id=analysis_id,
        evidence_items=items_list if items_list else raw_evidence,
        data_quality=dq,
    )

    ev_hash = calculate_evidence_hash(target_id, analysis_id, items_list)
    ev_id = f"EVD-{ev_hash[:10]}"

    return EvidenceBundle(
        evidence_id=ev_id,
        target_id=target_id,
        analysis_id=analysis_id,
        evidence_as_of=now_iso,
        items=tuple(items_list),
        why_am_i_seeing_this=narrative,
        data_quality=dq,
        limitations=("Data is derived from session-local completed analysis records.",),
        evidence_hash=ev_hash,
    )


def verify_evidence_freshness(
    bundle: EvidenceBundle,
    latest_record: Any,
    clock: Clock | None = None,
) -> bool:
    """Check if EvidenceBundle is still fresh relative to the latest completed analysis."""
    if not latest_record:
        return True

    rec_dict = latest_record.to_dict() if hasattr(latest_record, "to_dict") else dict(latest_record)
    rec_updated = str(rec_dict.get("updated_at") or rec_dict.get("created_at") or "")
    if not rec_updated:
        return True

    clk = clock or get_current_clock()
    bundle_dt = parse_timestamp_safe(bundle.evidence_as_of, default_time=clk.now())
    rec_dt = parse_timestamp_safe(rec_updated, default_time=clk.now())

    # Bundle is stale if record has been updated after bundle was created
    return bundle_dt >= rec_dt


def refresh_evidence_bundle(
    bundle: EvidenceBundle,
    latest_record: Any,
    clock: Clock | None = None,
) -> EvidenceBundle:
    """Regenerate EvidenceBundle from latest record state with updated timestamp."""
    clk = clock or get_current_clock()
    now_iso = clk.now_iso()

    target_mock = {
        "alert_id": bundle.target_id,
        "signal_id": bundle.target_id,
        "analysis_id": bundle.analysis_id,
        "data_quality": bundle.data_quality,
    }
    return build_evidence_bundle(target_mock, analysis_record=latest_record, clock=clk)
