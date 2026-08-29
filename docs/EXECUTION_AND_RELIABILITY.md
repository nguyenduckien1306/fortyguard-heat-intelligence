# FortyGuard Heat Intelligence — Execution State Machine & Reliability Invariants

This document specifies the execution lifecycle, bounded polling engine, timeout recovery, retry semantics, and core reliability invariants implemented across FortyGuard Heat Intelligence.

---

## 1. Centralized Execution State Machine

All thermal analysis tasks (Spatial Heatmap and Point Heat Intelligence) are executed through a pure, deterministic state machine (`frontend/utils/analysis_execution.py`).

```
                    ┌─────────────────────────┐
                    │           NEW           │
                    └────────────┬────────────┘
                                 │ Validation Succeeded (0 API calls)
                    ┌────────────▼────────────┐
                    │        VALIDATED        │
                    └────────────┬────────────┘
                                 │ User clicks "Run Analysis"
                    ┌────────────▼────────────┐
                    │       SUBMITTING        │
                    └────────────┬────────────┘
                                 │ HTTP POST (Returns activity_id)
                    ┌────────────▼────────────┐
       ┌───────────►│       PROCESSING        │◄───────────┐
       │            └────────────┬────────────┘            │
       │ Polling (GET)           │                         │
       │                         ├─────────────────────────┤
       │                         │                         │
┌──────┴──────┐           ┌──────▼──────┐           ┌──────▼──────┐
│  POLLING_   │           │  COMPLETED  │           │   FAILED    │
│   TIMEOUT   │           └─────────────┘           └─────────────┘
└──────┬──────┘
       │ "Check Again" (0 POSTs)
       └─────────────────────────┘
```

### State Definitions

| State | Semantic Meaning | Allowed Transitions | Credit Action |
|---|---|---|---|
| `NEW` | Initial input entry | $\to$ `VALIDATED` | 0 requests |
| `VALIDATED` | Input parameters mathematically confirmed valid | $\to$ `SUBMITTING` | 0 requests |
| `SUBMITTING` | HTTP `POST` dispatched to backend proxy | $\to$ `PROCESSING`, `FAILED` | 1 `POST` |
| `PROCESSING` | Asynchronous provider task in flight | $\to$ `COMPLETED`, `FAILED`, `POLLING_TIMEOUT` | Bounded `GET`s only |
| `COMPLETED` | Provider returned valid output; ingested to history | Terminal state for task | 0 requests |
| `FAILED` | Provider returned error code or rejected task | $\to$ `SUBMITTING` (Explicit Retry) | 0 requests until retry |
| `POLLING_TIMEOUT`| Observation window elapsed while still processing | $\to$ `PROCESSING` (Check Again), `SUBMITTING` (Retry) | 0 requests on Check Again |

---

## 2. Core Architectural & Reliability Invariants

### 1. Zero Network for Local Intelligence
- **Invariant**: All local intelligence operations (Watchlist evaluations, Operational Signal generation, Alert promotion, Priority scoring, Evidence Bundle generation, Scenario adjustments, Decision Brief exports) run **100% locally and in-memory**.
- **Enforcement**: Network mocking and firewall tests verify zero HTTP/HTTPS/socket calls across all local intelligence engines (`tests/test_operational_intelligence.py`, `tests/test_alert_engine.py`).

### 2. AnalysisRecord Immutability
- **Invariant**: Historical `AnalysisRecord` objects in `st.session_state` are strictly read-only after ingestion.
- **Enforcement**: No operation in the Watchlist Engine, Signal Pipeline, Alert Engine, or Investigation Queue mutates `AnalysisRecord` instances or their nested metric dictionaries.

### 3. Canonical Snapshot & Deterministic Hashing
- **Invariant**: Identical input records + watchlists + alert policies under the same timestamp produce **bit-for-bit identical outputs** and identical canonical SHA-256 snapshot hashes (`canonical_hash()`).
- **Enforcement**:
  - `IntelligenceSnapshot.canonical_hash()` sorts dictionary keys, serializes JSON with uniform separators, and calculates SHA-256 over all constituent entities.
  - Floating-point differences are rounded with canonical precision (`round(v, 4)`).

### 4. Credit Safety & Polling Isolation
- **Submission Invariant**: Exactly 1 user submission triggers at most 1 provider activity creation (`POST`).
- **Polling Invariant**: Status polling checks (`GET`) never consume task submission credits.
- **Check Again Invariant**: In observation timeout states, clicking **Check Again** polls the existing `activity_id` and performs **zero** new POST submissions.
- **Explicit Retry Invariant**: Clicking **Retry** displays an explicit credit consumption notice and creates Attempt $N+1$ linked to `parent_activity_id`. Zero automatic retries exist.

---

## 3. Observation Timeout & Retry Control

- **Observation Window**: Configurable via `POLLING_TIMEOUT_SECONDS = 120` (or up to 300s in settings).
- **Graceful Degradation**: If provider queues are congested, the platform does not treat timeout as a failure. Instead, it transitions to `POLLING_TIMEOUT` with user controls:
  - **`[ Check Again ]`**: Resumes polling on the existing `activity_id` (0 new submissions).
  - **`[ Start New Analysis ]`**: Resets the input form.
  - **`[ Retry Analysis ]`**: Explicitly submits a new attempt.

---

## 4. Signal Precedence & Alert Fatigue Protection

### Precedence Hierarchy
1. `WATCHLIST_MATCH` (Rank 6 — Highest)
2. `THRESHOLD_BREACH` (Rank 5)
3. `RAPID_CHANGE` (Rank 4)
4. `SIGNIFICANT_CHANGE` (Rank 3)
5. `REPEATED_HEAT` (Rank 2)
6. `DATA_ANOMALY` (Rank 1 — Lowest)

### Anti-Spam Cooldown & Hysteresis
- **Fatigue Protection**: Consecutive breaches within configured cooldown windows (15m, 1h, 6h, 24h) update escalation counters (`NORMAL` $\to$ `ELEVATED` $\to$ `HIGH` $\to$ `CRITICAL`) rather than generating duplicate alert records.
- **Anti-Flapping Hysteresis**: Dual-threshold evaluation (`trigger_threshold` vs `clear_threshold`) prevents rapid oscillation when metrics hover near boundary values.
