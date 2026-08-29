# FortyGuard Heat Intelligence — Export Engine & Decision Case Briefs

This document details the Export Engine, export formats (TXT and JSON), Decision Case Briefs, and the recursive sanitization pipeline.

---

## 1. What It Is & Why It Exists

The Export Engine (`frontend/utils/export.py`) generates audit-ready, shareable summaries of analyses, comparative findings, investigation cases, and operational snapshots. All exports include full cryptographic provenance while guaranteeing that sensitive credentials and signed URLs are completely sanitized.

---

## 2. Export Artifact Types

| Export Type | Source Component | Available Formats | Contents |
|---|---|---|---|
| **Analysis Export** | Analysis Workspace | TXT, JSON | Single analysis summary, metrics, data quality rating, tile counts |
| **Comparative Brief** | Decision Intelligence | TXT, JSON | Pairwise metric delta table ($\Delta \bar{T}$, $\Delta \text{Spread}$, $\Delta P_{\text{hot}}$), narrative insights |
| **Investigation Brief** | Investigation Queue | TXT, JSON | Queue case details, evidence bundle, audit trail, operator notes |
| **Decision Case Brief** | Command Center | TXT, JSON | Consolidated case brief: executive posture, active alerts, evidence hashes, disclaimers |

---

## 3. Recursive Sanitization Pipeline

Before any data structure is written to disk or sent to the browser for download, it is processed through deep recursive sanitization:
1. **Key Masking**: Any dictionary key matching `key`, `token`, `secret`, `auth`, or `password` is replaced with `"[REDACTED_SECRET]"`.
2. **URL Scrubbing**: Any cloud storage URL containing query parameters or signature hashes is replaced with `"[REDACTED_SECURE_SIGNED_URL]"`.
3. **Local Path Scrubbing**: Absolute file system paths are converted to relative workspace paths.
