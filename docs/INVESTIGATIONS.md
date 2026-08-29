# FortyGuard Heat Intelligence — Investigation Queue & Workflows

This document details the Investigation Queue, case lifecycle transitions, operator assignment workflows, and investigative briefs.

---

## 1. What It Is & Why It Exists

The Investigation Queue (`frontend/utils/investigation_queue.py`) provides structured operational incident management. When a signal or alert requires field verification or policy review, operators can add the item directly to the prioritized queue. This creates a traceable case record linking the alert to its source analysis, location, evidence hash, and operator notes.

---

## 2. Investigation Case Lifecycles

```
┌──────────────┐          ┌──────────────┐          ┌──────────────┐
│  STATUS_OPEN ├─────────►│  IN_REVIEW   ├─────────►│   RESOLVED   │
└──────┬───────┘          └──────────────┘          └──────────────┘
       │                                                   ▲
       └───────────────────────────────────────────────────┘
```

### Case States

| State | Action Available | Description |
|---|---|---|
| `STATUS_OPEN` | **`[ In Review ]`**, **`[ Open Analysis ]`** | New case waiting for operator assessment. |
| `STATUS_IN_REVIEW` | **`[ Resolve ]`**, **`[ Open Analysis ]`** | Case actively undergoing investigation or intervention. |
| `STATUS_RESOLVED` | **`[ Clear ]`** | Completed case with resolution notes recorded. |

---

## 3. Operator Actions & Evidence Inspection

Within the Investigation Queue tab:
- **Priority Badges**: Visual indicator (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) matching the signal priority score.
- **Direct Drilldown**: Clicking **Open** launches the full analysis inspection console for the underlying `AnalysisRecord`.
- **Operator Notes**: Persistent notes capture field findings, intervention dispatches, and verification timestamps.
- **Sanitized Export**: Individual cases can be exported as standalone Investigation Briefs (TXT or JSON).
