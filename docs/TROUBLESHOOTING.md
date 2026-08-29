# FortyGuard Heat Intelligence — Troubleshooting Guide

This guide provides diagnostic workflows and resolution steps for common technical issues encountered during local development, deployment, and testing.

---

## 1. Quick Diagnostic Checklist

Before troubleshooting individual components, verify:
- [ ] Virtual environment is activated (`(.venv)` prefix in terminal).
- [ ] FastAPI backend is running on `http://127.0.0.1:8000`.
- [ ] Health endpoint responds: `curl http://127.0.0.1:8000/api/v1/health`.
- [ ] `.env` file exists with valid configuration parameters.

---

## 2. Common Issues & Solutions

### Issue 1: "Unable to reach FastAPI backend" (Frontend Error)

**Symptom**: Streamlit displays an error indicating it cannot connect to the backend service.

**Cause**: The Uvicorn backend process is either not running, listening on an unexpected port, or blocked by a firewall.

**Resolution Steps**:
1. Check if the backend is running:
   ```powershell
   # Test backend root endpoint
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health"
   ```
2. If unreachable, start the backend in a dedicated terminal:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
3. Check if another process is occupying port 8000:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
   ```

---

### Issue 2: Port 8000 or 8501 Already in Use

**Symptom**: `ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)`.

**Resolution Steps (PowerShell)**:
1. Identify the Process ID (PID) holding the port:
   ```powershell
   Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess
   ```
2. Gracefully terminate the old process:
   ```powershell
   Stop-Process -Id <PID>
   ```
3. Restart the desired service.

---

### Issue 3: Heat Intelligence Analysis Stuck in "Processing"

**Symptom**: Analysis polling reaches observation timeout (default 120s or 300s) and displays `Still Processing`.

**Cause**: FortyGuard asynchronously processes large thermal modeling datasets. Queue times vary based on provider server load and spatial resolution.

**Resolution Steps**:
1. **Do NOT repeatedly resubmit**: Resubmission creates duplicate tasks and may consume additional API credits.
2. Click **`[ Check Again ]`** inside the Execution Console to query the existing `activity_id` (0 new submissions).
3. Expand the **Technical Details** expander to inspect the last provider status and check count.

---

### Issue 4: Task Returns "Failed" Status from Provider

**Symptom**: Execution Console transitions to red `Failed` state.

**Diagnosis**:
1. Expand the **Provider Failure Diagnostics** box inside the console.
2. Review the structured diagnostic fields:
   - `Code`: Error category (e.g., `INVALID_AOI`, `OUT_OF_BOUNDS`, `PROVIDER_UNAVAILABLE`).
   - `Message`: Human-readable description from FortyGuard.
   - `Details`: Specific parameters that caused rejection.

**Resolution Steps**:
1. If coordinates fall outside covered geographic regions, adjust the AOI polygon.
2. Click **`[ Retry Analysis ]`** to submit Attempt $N+1$ with corrected parameters.

---

### Issue 5: PDF Report Download Fails (HTTP 410 or Storage Error)

**Symptom**: Clicking **Download PDF Report** shows an error or returns corrupted data.

**Cause**: FortyGuard S3 download links expire after a temporary time-to-live (TTL).

**Resolution Steps**:
1. If the link expired (HTTP 410), click **`[ Check Again ]`** on the completed analysis to refresh the status payload.
2. Verify network connectivity to external cloud storage endpoints.

---

### Issue 6: Streamlit Duplicate Widget Key Warning

**Symptom**: `StreamlitDuplicateElementKey: There are multiple elements with the same key`.

**Cause**: A dynamic component or list item rendered without a unique `key` prefix.

**Resolution**:
- Ensure all loop-rendered buttons, inputs, and expanders append the item's unique identifier:
  ```python
  st.button("Inspect", key=f"_btn_inspect_{record.analysis_id}")
  ```

---

## 3. Diagnostic Commands Reference

```powershell
# Run full pytest suite with concise output
.venv\Scripts\python.exe -m pytest tests/ -q

# Run specific integration tests
.venv\Scripts\python.exe -m pytest tests/test_analysis_execution.py -v

# Verify FastAPI Swagger UI in browser
Start-Process "http://127.0.0.1:8000/docs"
```
