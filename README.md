# FortyGuard Heat Intelligence

An explainable heat intelligence and operational decision-support platform that turns provider-backed urban thermal analyses into actionable signals, alerts, prioritized investigations, cryptographic evidence bundles, and decision-ready reports.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40%2B-FF4B4B.svg)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/Tests-1528%20Passed-success.svg)](docs/TESTING.md)
[![Security](https://img.shields.io/badge/Security-Credential%20Isolated-blueviolet.svg)](docs/SECURITY.md)
[![Local Intelligence](https://img.shields.io/badge/Local%20Intelligence-Zero--Network-brightgreen.svg)](docs/ARCHITECTURE.md)

$$\text{Observe} \longrightarrow \text{Compare} \longrightarrow \text{Detect} \longrightarrow \text{Prioritize} \longrightarrow \text{Investigate} \longrightarrow \text{Explain} \longrightarrow \text{Decide}$$

---

## Table of Contents

- [Overview & The Problem](#overview--the-problem)
- [Core Capabilities](#core-capabilities)
- [Two Analysis Workflows](#two-analysis-workflows)
- [Signature Product Workflow](#signature-product-workflow)
- [Decision Intelligence & Comparisons](#decision-intelligence--comparisons)
- [Operational Command Center](#operational-command-center)
- [Signals, Priority & Alert Automation](#signals-priority--alert-automation)
- [Investigations & Evidence Provenance](#investigations--evidence-provenance)
- [Security & Credential Isolation](#security--credential-isolation)
- [Execution Reliability & Credit Safety](#execution-reliability--credit-safety)
- [Responsible Analytics](#responsible-analytics)
- [Quick Start Guide](#quick-start-guide)
- [Configuration](#configuration)
- [Project Architecture](#project-architecture)
- [Testing & Verification](#testing--verification)
- [Screenshots](#screenshots)
- [Demonstration Flow](#demonstration-flow)
- [Technical Documentation Index](#technical-documentation-index)
- [Technology Stack](#technology-stack)
- [Contributing & Code Quality](#contributing--code-quality)
- [Summary & Operational Value](#summary--operational-value)

---

## Overview & The Problem

Urban heat islands represent one of the most critical resilience and public environmental challenges facing modern metropolitan areas. While satellite data and temperature modeling APIs provide valuable data arrays, municipal planners and environmental operators face operational friction:

- **What was actually observed?** Raw GeoJSON arrays and thermal matrices require manual post-processing to extract actionable extremes, spatial spread, and threshold exceedances.
- **What changed over time?** Consecutive observations lack automated pairwise delta comparisons and trajectory tracking.
- **What deserves immediate attention?** Without policy-based alerting and explainable priority scoring, critical heat events are easily overlooked.
- **What evidence supports an intervention?** Operational decisions require transparent, audit-ready evidence with cryptographic provenance and historical context.

**FortyGuard Heat Intelligence** solves this by converting raw thermal observations into an automated operational decision support pipeline.

---

## Core Capabilities

### 🗺️ Spatial & Point Analysis

- **Heatmap Spatial Analysis**: Custom polygon Area of Interest (AOI) submission, GeoJSON thermal rendering, and interactive deck.gl map layers with dynamic color modes (Average, Minimum, Maximum temperature).
- **Heat Intelligence Point Analysis**: Multi-dimensional point-based observation analysis across confirmed categories with backend-proxied PDF report retrieval.
- **Centralized Execution State Machine**: Pure execution lifecycle engine (`NEW` $\to$ `VALIDATED` $\to$ `SUBMITTING` $\to$ `PROCESSING` $\to$ `COMPLETED` / `FAILED` / `POLLING_TIMEOUT`) with live timers and bounded status polling.

### 🧠 Decision & Cross-Analysis Intelligence

- **Sequential Change Detection**: Automatic delta computation comparing latest vs. preceding observations for identical locations or timelines.
- **Pairwise Matrix Comparison**: Side-by-side metric comparison ($\Delta T_{\text{mean}}$, $\Delta T_{\text{spread}}$, $\Delta P_{\text{hot}}$) across any two completed session records.
- **Cross-Analysis Pattern Detection**: Automated detection of recurring threshold exceedances, persistent thermal trajectories, signal concentrations, and data quality degradation.
- **Location Intelligence**: Geographic aggregation of analyses, active alert counts, and temperature ranges by distinct location labels.

### ⚡ Operations & Alerting

- **Proactive Watchlists**: Geographic and categorical monitoring rules with dual-threshold hysteresis to eliminate alert flapping.
- **Operational Signal Detection**: Deterministic detection of threshold exceedances, temperature jumps, high spatial spread, and data quality anomalies.
- **Explainable Priority Engine**: Transparent 0–100 mathematical scoring model combining base severity, exceedance magnitude, observation recency, persistence, and data quality multipliers.
- **Operator Attention Ranking**: Multi-factor urgency scoring ranking active alerts by immediate operational need.
- **Investigation Queue Console**: Prioritized assignment tracking (`OPEN` $\to$ `IN_REVIEW` $\to$ `RESOLVED`) with operator notes and direct inspection links.
- **Review Delta Tracking**: Instant visibility into what changed in the session since the operator last reviewed the Command Center.

### 🔍 Evidence & Provenance

- **Cryptographic Evidence Bundles**: Normalized observation parameters, threshold comparisons, and audit trails anchored by SHA-256 integrity hashes.
- **Sanitized Export Engine**: Downloadable Decision Case Briefs and Investigation Reports in structured Text and JSON formats.

### 🛡️ Reliability & Security

- **Strict Pre-Flight Validation**: Pure mathematical validation for coordinates, polygons, dates, and temperatures preventing invalid API submissions (0 wasted credits).
- **Backend Credential Isolation**: The frontend client never receives, stores, or handles provider API keys.
- **Signed Storage URL Proxying**: S3 report links are fetched exclusively by the backend and streamed to the browser as raw binary streams.
- **Zero-Network Local Intelligence**: Once an analysis is completed, all local intelligence operations (comparisons, signals, alerts, queues, scenarios, exports) execute 100% locally with zero external network requests.

---

## Two Analysis Workflows

| Capability          | Heatmap Spatial Analysis                                              | Heat Intelligence Point Analysis                  |
| ------------------- | --------------------------------------------------------------------- | ------------------------------------------------- |
| **Input Type**      | Area of Interest (AOI) Polygon ($\ge 4$ coordinates)                  | Single Geographic Point (Latitude / Longitude)    |
| **Parameters**      | Date, Time (HH:MM), Granularity ($10\text{m} \le g \le 1000\text{m}$) | Date, Observed Temp, Analysis Category Dimensions |
| **Visualization**   | Interactive deck.gl polygon tile map with tooltips                    | Environmental point metrics & summary review      |
| **Analytics**       | Min, Mean, Max, Spread, Hot-Area Proportion ($P_{\text{hot}}$)        | Multi-factor category breakdown                   |
| **Output Artifact** | Ingested `AnalysisRecord` with GeoJSON feature collections            | Ingested `AnalysisRecord` + Proxied PDF Report    |

_See [docs/HEATMAP_ANALYSIS.md](docs/HEATMAP_ANALYSIS.md) and [docs/HEAT_INTELLIGENCE.md](docs/HEAT_INTELLIGENCE.md) for full specifications._

---

## Signature Product Workflow

```
User Input & Geometry
       │
       ▼
Pre-Flight Validation  ─────────► [Invalid Input: 0 API Calls]
       │ (Valid Only)
       ▼
FastAPI Backend Proxy
       │ (Injects api-key Header)
       ▼
FortyGuard Enterprise API  ─────► Async Task Execution & Polling
       │ (Completed)
       ▼
AnalysisRecord Ingestion  ──────► In-Memory Session History
       │
       ├──────────────────────────────────────────────────────┐
       ▼                                                      ▼
Decision Intelligence                              Operational Command Center
- Pairwise Metric Comparisons                      - Watchlist Evaluations
- Change Since Last Observation                    - Operational Signal Detection
- Cross-Analysis Pattern Detection                 - 0–100 Priority Scoring
- Location-Centric Aggregations                    - Alert Lifecycle & Cooldown
- Scenario Sandbox (What-If Adjustments)           - Operator Attention Ranking
       │                                           - Investigation Queue Console
       │                                                      │
       └──────────────────────────┬───────────────────────────┘
                                  ▼
                     Evidence Bundles & Provenance
                     (SHA-256 Anchored Audit Trail)
                                  │
                                  ▼
                Decision Case Brief Exports (TXT / JSON)
```

---

## Decision Intelligence & Comparisons

The platform provides longitudinal analysis across completed records without making new external API requests:

- **Pairwise Matrix Comparison**: Compares two analyses side-by-side to compute exact metric deltas:
  $$\Delta \bar{T} = \bar{T}_B - \bar{T}_A, \quad \Delta \text{Spread} = \Delta T_B - \Delta T_A, \quad \Delta P_{\text{hot}} = P_{\text{hot}, B} - P_{\text{hot}, A}$$
- **Change Detection Breakdown**: Highlights newly triggered policy conditions and data quality transitions between consecutive observations.
- **Pattern Recognition**: Continuously checks session history for repeated thermal exceedances, sustained temperature increases, and signal concentrations.

_See [docs/DECISION_INTELLIGENCE.md](docs/DECISION_INTELLIGENCE.md)._

---

## Operational Command Center

The Command Center (`frontend/pages/dashboard.py`) provides an executive view across 8 analytical workspaces:

1. **Command Center (Home)**: Executive operational posture briefing, sequential change deltas, attention-ranked alerts, and priority signals.
2. **Watchlists Dashboard**: Multi-criteria monitoring rules with hysteresis controls.
3. **Signal Center**: Raw detected signals with explanatory priority breakdowns.
4. **Alert Center**: Promoted alert items with lifecycle status management (`NEW`, `ACKNOWLEDGED`, `RESOLVED`).
5. **Investigation Queue**: Case management backlog with operator notes and export tools.
6. **Analysis Workspace**: Full session history search, filtering, tagging, and pinning.
7. **Scenario Sandbox**: Hypothetical what-if parameter delta modeling with non-persisting adjustments.
8. **Intelligence Diagnostics**: Real-time SHA-256 snapshot hashes, zero-network verification counters, and structured audit logs.

_See [docs/OPERATIONAL_COMMAND_CENTER.md](docs/OPERATIONAL_COMMAND_CENTER.md)._

---

## Signals, Priority & Alert Automation

### Deterministic Priority Scoring (0–100 Model)

Priority scores are calculated via an explainable mathematical formula (`frontend/utils/priority.py`):

$$\text{Priority Score} = \min\left(100.0, \, \max\left(0.0, \, \left(\text{Base}_{\text{sev}} + \text{Pts}_{\text{mag}} + \text{Pts}_{\text{rec}} + \text{Pts}_{\text{per}}\right) \times \text{Mult}_{\text{dq}}\right)\right)$$

- **Severity Base**: `CRITICAL` (40 pts), `ELEVATED` (30 pts), `WATCH` (20 pts), `INFO` (10 pts).
- **Magnitude Points**: Exceedance distance normalized over a $5.0^\circ\text{C}$ range (0–30 pts).
- **Recency Points**: Observation recency decay (2–15 pts).
- **Persistence Points**: Recurring thermal trajectory bonus (0–15 pts).
- **Data Quality Multiplier**: `HIGH` (1.00), `MEDIUM` (0.85), `LOW` (0.70), `INSUFFICIENT` (0.40).

### Alert Lifecycle & Fatigue Protection

- **Cooldown Windows**: Configurable durations (15m, 1h, 6h, 24h) prevent duplicate alert spam.
- **Anti-Flapping Hysteresis**: Dual-threshold evaluation (`trigger_threshold` vs `clear_threshold`) stabilizes alerts during temperature oscillations.

_See [docs/ALERTS_AND_SIGNALS.md](docs/ALERTS_AND_SIGNALS.md) and [docs/WATCHLISTS.md](docs/WATCHLISTS.md)._

---

## Investigations & Evidence Provenance

Every operational indicator and investigation case is anchored by an immutable Evidence Bundle (`frontend/utils/evidence_bundle.py`):

```json
{
  "bundle_id": "ev_20260829_001",
  "analysis_id": "HM-20260829-001",
  "observed_value": 38.4,
  "threshold_value": 35.0,
  "exceedance": 3.4,
  "data_quality": "HIGH",
  "audit_trail": {
    "activity_id": "act_heatmap_123",
    "total_tiles": 84,
    "valid_tiles": 84
  },
  "evidence_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

_See [docs/INVESTIGATIONS.md](docs/INVESTIGATIONS.md) and [docs/EVIDENCE_AND_PROVENANCE.md](docs/EVIDENCE_AND_PROVENANCE.md)._

---

## Security & Credential Isolation

```
┌────────────────────────────────────────────────────────────────────────┐
│ STREAMLIT FRONTEND                                                     │
│ - Zero provider API keys stored or accessible in memory                │
│ - Zero direct external HTTP calls to api.fortyguard.com                │
│ - Local session-only state storage (st.session_state)                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP Requests (localhost:8000)
┌───────────────────────────────────▼────────────────────────────────────┐
│ FASTAPI BACKEND                                                        │
│ - Sole holder of FORTYGUARD_API_KEY (read from .env)                   │
│ - Injects 'api-key' header exclusively in backend client               │
│ - Proxies S3 PDF downloads (signed URLs never reach browser)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS (api.fortyguard.com)
┌───────────────────────────────────▼────────────────────────────────────┐
│ FORTYGUARD ENTERPRISE API                                              │
└────────────────────────────────────────────────────────────────────────┘
```

- **Backend-Only Keys**: The browser never handles or receives provider credentials.
- **Signed URL Isolation**: Temporary S3 links are retrieved and streamed directly through FastAPI; the browser never sees the raw storage URL.
- **Recursive Sanitization**: Exports and technical inspection expanders automatically redact any key, token, or storage link query parameter.

_See [docs/SECURITY.md](docs/SECURITY.md)._

---

## Execution Reliability & Credit Safety

- **1 User Submission = At Most 1 Provider Task**: Valid submissions trigger exactly 1 `POST` request.
- **Zero-Credit Status Polling**: Bounded polling uses `GET` status requests that do not consume task creation credits.
- **Check Again Gating**: In observation timeout states, checking status queries the existing `activity_id` without creating new tasks.
- **Explicit User Retry**: Retries require explicit user confirmation and create Attempt $N+1$ linked to the parent task.

_See [docs/EXECUTION_AND_RELIABILITY.md](docs/EXECUTION_AND_RELIABILITY.md)._

---

## Responsible Analytics

All derived metrics, insights, and summaries generated by the platform adhere to strict non-causal standards (`frontend/utils/responsible_analytics.py`):

> **Non-Causal Analytical Standard**: The platform generates descriptive analytical observations from confirmed sensor and satellite modeling data. It does **not** assert causality, clinical diagnoses, medical heat risks, or predictive microclimate guarantees.

_See [docs/ANALYTICS.md](docs/ANALYTICS.md)._

---

## Quick Start Guide

### 1. Activate Environment

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```cmd
.\.venv\Scripts\activate.bat
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and set your FortyGuard API credentials:

```powershell
Copy-Item .env.example .env
```

### 3. Start FastAPI Backend

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Verify backend health:

```powershell
curl http://127.0.0.1:8000/api/v1/health
```

### 4. Start Streamlit Frontend

In a separate terminal:

```powershell
.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.port 8501
```

Open your browser at **`http://localhost:8501`**.

_See [docs/OPERATIONS.md](docs/OPERATIONS.md)._

---

## Configuration

Configuration parameters are managed via Pydantic Settings in `backend/config.py` using `.env`:

| Variable                   | Required                  | Default                      | Purpose                                                                   |
| -------------------------- | ------------------------- | ---------------------------- | ------------------------------------------------------------------------- |
| `FORTYGUARD_API_KEY`       | No (Demo mode if omitted) | `""`                         | Enterprise API key for FortyGuard authentication                          |
| `FORTYGUARD_BASE_URL`      | No                        | `https://api.fortyguard.com` | Base URL for FortyGuard Enterprise REST API                               |
| `APP_ENV`                  | No                        | `development`                | Runtime environment name (`development` / `production`)                   |
| `LOG_LEVEL`                | No                        | `INFO`                       | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)                   |
| `MAX_HISTORY_RECORDS`      | No                        | `50`                         | Maximum session history records retained in memory                        |
| `MAX_WATCHLISTS`           | No                        | `20`                         | Maximum active watchlists per browser session                             |
| `MAX_ALERTS`               | No                        | `50`                         | Maximum active alerts retained in alert center                            |
| `MAX_QUEUE_ITEMS`          | No                        | `100`                        | Maximum items permitted in the investigation queue                        |
| `POLLING_TIMEOUT_SECONDS`  | No                        | `120`                        | Observation timeout threshold before transitioning to non-failing timeout |
| `POLLING_INTERVAL_SECONDS` | No                        | `2.0`                        | Default interval between task status polling requests                     |

---

## Project Architecture

```
FortyGuard-Heat-Intelligence/
├── backend/                        # FastAPI Backend Service
│   ├── api/                        # FortyGuard API client & error mapping
│   ├── models/                     # Pydantic request/response schemas
│   ├── routes/                     # REST endpoints (health, heatmap, heat_intelligence)
│   ├── services/                   # Domain services & bounded polling orchestration
│   └── config.py                   # Pydantic Settings & secret redaction
├── frontend/                       # Streamlit Analytical Application
│   ├── app.py                      # Application entry point & theme injection
│   ├── pages/                      # Page modules (dashboard, heatmap, heat_intelligence)
│   ├── components/                 # UI components (design system, consoles, alerts)
│   └── utils/                      # Local intelligence engines (signals, queue, priority)
├── docs/                           # Technical Documentation Package
│   ├── ARCHITECTURE.md             # System architecture & component boundaries
│   ├── SECURITY.md                 # Threat model, secret isolation, & PDF proxy
│   ├── ANALYTICS.md                # Metric formulations & priority scoring math
│   ├── OPERATIONS.md               # Runbook, service ports, & diagnostic matrix
│   ├── TROUBLESHOOTING.md          # Diagnostic guides & common issue resolution
│   ├── TESTING.md                  # Test suite hierarchy & invariant verification
│   ├── HEATMAP_ANALYSIS.md         # Spatial analysis & deck.gl rendering
│   ├── HEAT_INTELLIGENCE.md        # Point analysis & proxied PDF reporting
│   ├── DECISION_INTELLIGENCE.md    # Pairwise comparison & pattern detection
│   ├── OPERATIONAL_COMMAND_CENTER.md # 8-tab Command Center & executive posture
│   ├── WATCHLISTS.md               # Monitoring criteria & hysteresis
│   ├── ALERTS_AND_SIGNALS.md       # Signal detection & priority scoring
│   ├── INVESTIGATIONS.md           # Queue management & operator actions
│   ├── EVIDENCE_AND_PROVENANCE.md  # Evidence bundles & SHA-256 hashing
│   ├── EXECUTION_AND_RELIABILITY.md# State machine & reliability invariants
│   ├── EXPORTS.md                  # Sanitized TXT/JSON decision case briefs
│   └── DEMO_GUIDE.md               # 3–5 minute presentation walkthrough script
├── tests/                          # Automated Pytest Test Suite (90 files, 1528 tests)
├── main.py                         # FastAPI server entry point
├── requirements.txt                # Python package dependencies
└── .env.example                    # Example environment configuration
```

---

## Testing & Verification

The repository includes a comprehensive, verified test suite comprising **1,528 tests across 90 test files** with 100% pass rate:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

### Verified Test Categories

- **Pre-flight Validation**: Strict boundary checks for coordinates, dates, temperatures, and polygons.
- **Execution State Machine**: Verification of polling safety, timeout transitions, and explicit retry semantics.
- **Zero-Network Invariants**: Asserting zero external HTTP calls during local intelligence operations.
- **Security & Redaction**: Automated audits ensuring zero secrets or signed storage URLs in export briefs.
- **Hostile Failure Injection**: Resilience tests covering malformed responses, transport drops, and NaN/Inf metrics.

_See [docs/TESTING.md](docs/TESTING.md)._

---

## Screenshots

> _Add application UI screenshots to `docs/images/` prior to public distribution._

1. **Operational Command Center**: Executive posture, active signals, and review deltas.
2. **Heatmap Spatial Analysis**: High-resolution deck.gl polygon thermal visualization.
3. **Heat Intelligence Point Analysis**: Multi-dimensional point observation inputs and PDF report download.
4. **Decision Intelligence**: Side-by-side pairwise comparative matrix.
5. **Investigation Queue**: Case tracking, operator notes, and evidence audit trails.
6. **Scenario Sandbox**: Hypothetical what-if simulation adjustments.

---

## Demonstration Flow

A structured 3–5 minute demonstration of the product follows:

1. **Run Analysis**: Submit a spatial Heatmap or point Heat Intelligence observation.
2. **Review Output**: Inspect the interactive thermal map layer or environmental point metrics.
3. **Command Center**: Review the executive posture summary and auto-detected operational signals.
4. **Examine Priority**: Expand the explainable mathematical scoring breakdown for elevated signals.
5. **Inspect Evidence**: Review the cryptographically hashed Evidence Bundle and source audit trail.
6. **Add to Investigation**: Promote the signal to the Investigation Queue and assign operator notes.
7. **Decision Intelligence**: Run a pairwise comparison between two completed session observations.
8. **Scenario Sandbox**: Adjust what-if parameters to model hypothetical policy changes.
9. **Export Decision Brief**: Download an audit-ready Decision Case Brief in TXT or JSON format.

_See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)._

---

## Technical Documentation Index

| Technical Document                                               | Topic & Focus Area                                                      |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| [System Architecture](docs/ARCHITECTURE.md)                      | Component boundaries, data flow diagrams, and state machines            |
| [Security & Threat Model](docs/SECURITY.md)                      | Credential isolation, PDF proxy architecture, and sanitization          |
| [Analytical Stack](docs/ANALYTICS.md)                            | Priority scoring formulas, signal detection, and data quality metrics   |
| [Operations Runbook](docs/OPERATIONS.md)                         | Startup procedures, failure mode matrix, and port topology              |
| [Troubleshooting Guide](docs/TROUBLESHOOTING.md)                 | Diagnostic workflows, port conflict resolution, and error codes         |
| [Testing Strategy](docs/TESTING.md)                              | Test organization, invariant verification, and execution commands       |
| [Heatmap Spatial Analysis](docs/HEATMAP_ANALYSIS.md)             | Spatial polygon analysis, validation, and deck.gl layer rendering       |
| [Heat Intelligence Point Analysis](docs/HEAT_INTELLIGENCE.md)    | Point observations, category dimensions, and proxied PDF downloads      |
| [Decision Intelligence](docs/DECISION_INTELLIGENCE.md)           | Pairwise comparisons, sequential change tracking, and pattern detection |
| [Operational Command Center](docs/OPERATIONAL_COMMAND_CENTER.md) | 8-tab Command Center, executive summaries, and review deltas            |
| [Watchlists & Monitoring](docs/WATCHLISTS.md)                    | Geographic criteria configuration and anti-flapping hysteresis          |
| [Signals & Alert Automation](docs/ALERTS_AND_SIGNALS.md)         | Signal detection pipeline, priority weights, and cooldown windows       |
| [Investigation Workflows](docs/INVESTIGATIONS.md)                | Prioritized queue lifecycle, operator assignments, and notes            |
| [Evidence & Provenance](docs/EVIDENCE_AND_PROVENANCE.md)         | Evidence bundles, SHA-256 integrity hashing, and freshness              |
| [Execution & Reliability](docs/EXECUTION_AND_RELIABILITY.md)     | State machine, observation timeouts, and credit safety                  |
| [Export Engine](docs/EXPORTS.md)                                 | Decision Case Briefs, comparative reports, and sanitization             |
| [Demo Guide](docs/DEMO_GUIDE.md)                                 | Structured 3–5 minute presentation walkthrough script                   |

---

## Technology Stack

```
Frontend               Backend                Provider Integration     Testing & Quality
────────               ───────                ────────────────────     ─────────────────
• Streamlit 1.40+      • FastAPI 0.115+       • FortyGuard REST API    • Pytest 8.3+
• Deck.gl (Pydeck)     • Uvicorn (ASGI)       • Bounded Async Polling  • Streamlit AppTest
• Custom CSS Tokens    • Pydantic Settings    • S3 Streaming Proxy     • Zero-Network Invariant Audits
• Space Grotesk / Mono • Strict Validation    • Secret Redaction       • Hostile Failure Injection
```

---

## Contributing & Code Quality

1. **Deterministic Execution**: All local intelligence engines must remain 100% deterministic and session-local.
2. **Zero Network Leakage**: Never introduce external HTTP/HTTPS calls into local calculation pipelines (`utils/`).
3. **Secret Isolation**: Never expose provider API keys, tokens, or signed storage URLs to frontend state or exported artifacts.
4. **Non-Causal Analytics**: Adhere strictly to Responsible Analytics standards without asserting unproven medical or causal claims.
5. **Test Coverage**: Run the automated test suite prior to submitting changes:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -q
   ```

---

## Summary & Operational Value

FortyGuard Heat Intelligence transforms urban thermal data from static visualization into an **explainable, proactive operational decision engine**:

- **For City Planners**: Track neighborhood thermal trajectories, evaluate vegetative cooling impact, and compare longitudinal interventions.
- **For Emergency Services**: Receive automated threshold alerts, fatigue-protected escalations, and priority-ranked response targets.
- **For Environmental Analysts**: Generate cryptographic evidence bundles and audit-ready decision briefs with full provenance.

---

<div align="center">

**FortyGuard Heat Intelligence** · Urban Thermal Analytics & Multi-Factor Resilience Platform  
*Built for explainable decision support, zero-network local intelligence, and enterprise security.*

<br />

**Lead Developer**: **Muhammad Abdullah**  
**Developer**: **Abdul Rehman**

</div>
