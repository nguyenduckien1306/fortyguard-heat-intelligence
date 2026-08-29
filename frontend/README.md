# Streamlit Frontend

Phase 3 Streamlit workflow for the FortyGuard Heat Intelligence dashboard.

## Overview

**Streamlit** is the frontend for this project. It communicates exclusively with our **FastAPI backend** — it must **never** contain FortyGuard API keys or call the FortyGuard API directly.

```
Streamlit  →  HTTP  →  FastAPI  →  FortyGuardClient  →  FortyGuard API
```

## Entry point

```bash
streamlit run frontend/app.py
```

From the project root with the virtual environment activated.

## Structure

| Path | Purpose |
|------|---------|
| `app.py` | Streamlit application entry point |
| `components/` | Reusable UI (sidebar, metrics, map, charts, status) |
| `pages/` | Dashboard and Heat Intelligence page layouts |
| `services/api.py` | HTTP client for the FastAPI backend |
| `utils/formatting.py` | Display formatting helpers |

## Current status

The Heat Intelligence page accepts the documented GeoJSON Polygon
FeatureCollection, date/time values, and granularity. It reviews the request,
submits through FastAPI, and tracks Processing, Completed, Failed, and error
states. A Completed result is rendered as a map, statistics, and metadata via
an internal adapter (`backend/models/heatmap_result.py`) that treats
FortyGuard's undocumented result shape defensively and never fabricates
values. Since no live request has been made yet, a dev-only "preview with
mock result" toggle renders the same UI against local fixtures
(`backend/mock_data/heatmap_results.py`) — no network calls. The frontend
never calls FortyGuard directly.

## Security

- Do **not** put `FORTYGUARD_API_KEY` in Streamlit code or `frontend/.streamlit/secrets.toml` in source control.
- Backend handles all FortyGuard communication and credential loading from `.env`.

## Optional configuration

Set the backend URL if FastAPI is not on the default host:

```powershell
$env:BACKEND_API_BASE_URL = "http://localhost:8000"
```
