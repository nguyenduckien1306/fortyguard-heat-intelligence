# FortyGuard Heat Intelligence — Evidence Bundles & Provenance

This document details Evidence Bundles, cryptographic integrity hashing, audit trail tracking, and data freshness validation.

---

## 1. What It Is & Why It Exists

To support defensible decision-making, every operational indicator, alert, and investigation case is accompanied by a cryptographic Evidence Bundle (`frontend/utils/evidence_bundle.py`). This guarantees that every operational alert links directly to confirmed ground-truth data with unforgeable provenance.

---

## 2. Structure of an Evidence Bundle

```json
{
  "bundle_id": "ev_20260829_001",
  "analysis_id": "HM-20260829-001",
  "signal_id": "sig_thresh_001",
  "evidence_as_of": "2026-08-29T14:00:00Z",
  "observed_value": 38.40,
  "threshold_value": 35.00,
  "exceedance": 3.40,
  "data_quality": "HIGH",
  "location_label": "Financial District",
  "audit_trail": {
    "activity_id": "act_heatmap_123",
    "granularity_meters": 100,
    "total_tiles": 84,
    "valid_tiles": 84
  },
  "evidence_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

---

## 3. Cryptographic Integrity Hashing

The `evidence_hash` is computed as a SHA-256 digest over the normalized, sorted dictionary representation of the observed metrics, threshold parameters, and audit metadata.

### Determinism & Freshness Guarantee
- **Canonical Sorting**: Keys are sorted deterministically before hashing.
- **Freshness Invariant**: If an `AnalysisRecord` is updated or modified after `evidence_as_of`, `bundle.is_stale(record)` flags `True`, alerting operators that evidence must be refreshed.
