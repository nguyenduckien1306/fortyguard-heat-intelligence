# FortyGuard Heat Intelligence — Operations & Runbook

This document details day-to-day operational procedures, server execution, health probes, failure mode diagnostics, and session maintenance for the FortyGuard Heat Intelligence platform.

---

## 1. Service Port & Network Topology

| Component | Default Port | Protocol | Binding Address | Description |
|---|---|---|---|---|
| **FastAPI Backend** | `8000` | HTTP | `127.0.0.1` | REST API, validation, FortyGuard client, PDF proxy |
| **Streamlit Frontend** | `8501` | HTTP | `localhost` | Analytical UI, Command Center, visualization |

---

## 2. Startup Procedures

### Prerequisites

Ensure the Python virtual environment is activated and `.env` is configured with a valid `FORTYGUARD_API_KEY` (or run in demo/mock mode).

```powershell
# 1. Activate environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Or Windows Command Prompt
.\.venv\Scripts\activate.bat
```

### Step 1: Start the FastAPI Backend

```powershell
# Run Uvicorn server on port 8000
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### Step 2: Verify Backend Health

```powershell
# In a separate terminal or browser
curl http://127.0.0.1:8000/api/v1/health
```

Expected healthy response:
```json
{
  "status": "healthy",
  "service": "FortyGuard Heat Intelligence",
  "version": "2.0.0",
  "environment": "development",
  "fortyguard_api_configured": true,
  "fortyguard_base_url": "https://api.fortyguard.com"
}
```

### Step 3: Start the Streamlit Frontend

```powershell
# Launch Streamlit frontend on port 8501
.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.port 8501
```

Access the UI at **`http://localhost:8501`**.

---

## 3. Analysis Processing Lifecycles

### Normal Execution Lifecycle

1. **Parameter Entry**: User configures AOI polygon (Heatmap) or coordinates + dimensions (Heat Intelligence).
2. **Pre-flight Validation**: Client-side validation verifies parameters. Invalid inputs block submission locally (0 API calls).
3. **Task Submission**: Backend sends `POST` request to FortyGuard and receives an `activity_id`.
4. **Bounded Polling**: Streamlit polls `GET /status/{activity_id}` every 2 seconds. The Execution Console displays elapsed time and polling attempt counts.
5. **Completion & Ingestion**: When the task returns `status: "Completed"`, the result is validated and stored in session history.

### Observation Timeout Handling

- **Default Timeout**: Configured via `POLLING_TIMEOUT_SECONDS = 120` (or up to 300s in settings).
- **Behavior**: If FortyGuard is still processing when the observation window expires, the UI transitions to **`Still Processing (Observation Timeout)`**.
- **Action Options**:
  - **`[ Check Again ]`**: Polls the existing `activity_id` immediately. Performs **zero** new POST requests.
  - **`[ Start New Analysis ]`**: Resets the execution console for new parameter input.
  - **`[ Retry ]`**: Creates an explicit Attempt $N+1$ linked to the parent task.

---

## 4. Failure Mode Matrix & Diagnosis

```
                    ┌─────────────────────────┐
                    │    Operation Error      │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌────────▼────────┐     ┌────────▼────────┐     ┌────────▼────────┐
│ Validation Error│     │ Backend Unreach │     │ Provider Error  │
│ (Pre-submission)│     │ (Network/Port)  │     │ (Async Task)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

| Failure State | Root Cause | Observable Symptoms | Recommended Action |
|---|---|---|---|
| **Validation Failure** | Invalid polygon ring, out-of-bounds coordinates, empty dimensions | Red inline warning under input; Submit button blocked | Correct coordinates or close polygon geometry. |
| **Backend Unavailable** | FastAPI process not running or blocked on port 8000 | Frontend displays "Unable to reach FastAPI backend" | Check Uvicorn process; verify port 8000 is open. |
| **Provider Unconfigured** | Missing `FORTYGUARD_API_KEY` in `.env` | Health check returns `"provider_configured": false` | Supply API key in `.env` or use mock/demo mode. |
| **Provider Processing** | Normal asynchronous queueing at FortyGuard | Status shows `Processing`, timer increments | Wait for task completion or use "Check Again". |
| **Provider Task Failed** | Provider rejected parameters or service exception | Status shows `Failed`; Diagnostic box shows code/reason | Review diagnostic details; check AOI coverage; click Retry. |
| **PDF Download Error** | Expired signed URL (HTTP 410) or storage connectivity | Error alert on PDF download button | Re-poll status to refresh signed link or contact provider. |

---

## 5. Session Management & Reset Semantics

- **In-Memory History**: Session history is stored in `st.session_state` and capped at `MAX_HISTORY_RECORDS = 50`.
- **Clearing Session**:
  - Click **Workspace Management (Clear History)** inside the Analysis Workspace tab.
  - Alternatively, refreshing the browser tab with cache clear clears all active session states.
- **Graceful Shutdown**:
  - Terminate processes using `Ctrl+C` in both terminal windows.
