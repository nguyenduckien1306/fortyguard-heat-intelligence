"""Phase 6C — Controlled live Heat Intelligence request using the documented schema from docs-api.fortyguard.com.

Endpoint: POST https://api.fortyguard.com/v1/heat_intelligence
Payload:
{
    "latitude": 40.7050,
    "longitude": -74.0090,
    "temperature": 32.5,
    "date": "2024-07-15",
    "analysis": ["environmental"]
}
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.client import FortyGuardClient
from backend.config import get_settings


def main() -> None:
    settings = get_settings()

    if not settings.fortyguard_api_configured:
        print("ERROR: FortyGuard API key is not configured in .env")
        sys.exit(1)

    print("=" * 70)
    print("PHASE 6C — Documented Heat Intelligence Live Discovery (/v1/heat_intelligence)")
    print("=" * 70)
    print(f"Base URL: {settings.fortyguard_base_url}")
    print("API key configured: YES (value hidden)")
    print()

    # Documented payload for /v1/heat_intelligence
    submitted_payload = {
        "latitude": 40.7050,
        "longitude": -74.0090,
        "temperature": 32.5,
        "date": "2024-07-15",
        "analysis": ["environmental"],
    }

    print("Target Endpoint: POST https://api.fortyguard.com/v1/heat_intelligence")
    print("Submitted payload:")
    print(json.dumps(submitted_payload, indent=2))
    print()

    trace: dict = {
        "discovery_type": "heat_intelligence_documented",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/v1/heat_intelligence",
        "submitted_payload": submitted_payload,
        "submission_http_status": None,
        "initial_response": None,
        "activity_id": None,
        "polling_history": [],
        "final_status": None,
        "final_response": None,
    }

    client = FortyGuardClient(settings=settings)

    # ── STEP 1: Exactly one POST submission to /v1/heat_intelligence ──
    print("Submitting POST /v1/heat_intelligence ...")
    t0 = time.monotonic()
    try:
        raw_response = client._http_client.post(
            "/v1/heat_intelligence",
            json=submitted_payload,
        )
        submission_elapsed = time.monotonic() - t0
        trace["submission_http_status"] = raw_response.status_code
        print(f"  HTTP status: {raw_response.status_code}")
        print(f"  Elapsed: {submission_elapsed:.2f}s")

        try:
            initial_body = raw_response.json()
        except Exception:
            initial_body = raw_response.text
        trace["initial_response"] = initial_body
        print(f"  Response body: {json.dumps(initial_body, indent=2) if isinstance(initial_body, dict) else initial_body}")

        if raw_response.status_code >= 400:
            print(f"\nSUBMISSION RETURNED HTTP {raw_response.status_code}")
            _save_trace(trace)
            return

        # Extract activity_id
        if isinstance(initial_body, dict):
            data_section = initial_body.get("data", {})
            if isinstance(data_section, dict):
                activity_id = data_section.get("activity_id")
            else:
                activity_id = None
        else:
            activity_id = None

        if not activity_id:
            print("\nNOTE: No activity_id in submission response")
            _save_trace(trace)
            return

        trace["activity_id"] = activity_id
        print(f"\n  Activity ID: {activity_id}")

    except Exception as exc:
        submission_elapsed = time.monotonic() - t0
        print(f"  EXCEPTION during submission: {exc}")
        trace["submission_http_status"] = "EXCEPTION"
        trace["initial_response"] = str(exc)
        _save_trace(trace)
        return

    # ── STEP 2: Bounded polling if activity_id received ──
    print(f"\nPolling GET /v1/status/{activity_id} ...")
    MAX_ATTEMPTS = 60
    POLL_INTERVAL = 3.0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        poll_start = time.monotonic()
        try:
            status_response = client._http_client.get(f"/v1/status/{activity_id}")
            poll_elapsed = time.monotonic() - poll_start
            try:
                status_body = status_response.json()
            except Exception:
                status_body = status_response.text

            poll_entry = {
                "attempt": attempt,
                "http_status": status_response.status_code,
                "elapsed_seconds": round(poll_elapsed, 3),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "response": status_body,
            }
            trace["polling_history"].append(poll_entry)

            if isinstance(status_body, dict):
                data = status_body.get("data", {})
                if isinstance(data, dict):
                    current_status = data.get("status", "Unknown")
                else:
                    current_status = "Unknown"
            else:
                current_status = "Unknown"

            total_elapsed = time.monotonic() - t0
            print(f"  [{attempt}/{MAX_ATTEMPTS}] Status: {current_status} ({poll_elapsed:.2f}s, total {total_elapsed:.1f}s)")

            if current_status == "Completed":
                trace["final_status"] = "Completed"
                trace["final_response"] = status_body
                print(f"\n{'=' * 60}")
                print("TASK COMPLETED")
                print(f"{'=' * 60}")
                print(f"Total elapsed: {total_elapsed:.1f}s")
                print("Result:\n", json.dumps(data.get("result"), indent=2))
                break

            elif current_status == "Failed":
                trace["final_status"] = "Failed"
                trace["final_response"] = status_body
                print(f"\nTASK FAILED: {status_body}")
                break

            elif current_status == "Unknown":
                trace["final_status"] = "Unknown"
                trace["final_response"] = status_body
                break

            if attempt < MAX_ATTEMPTS:
                time.sleep(POLL_INTERVAL)

        except Exception as exc:
            poll_elapsed = time.monotonic() - poll_start
            poll_entry = {
                "attempt": attempt,
                "http_status": "EXCEPTION",
                "elapsed_seconds": round(poll_elapsed, 3),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "response": str(exc),
            }
            trace["polling_history"].append(poll_entry)
            print(f"  [{attempt}] EXCEPTION: {exc}")
            break
    else:
        trace["final_status"] = "Timeout"
        trace["final_response"] = trace["polling_history"][-1]["response"] if trace["polling_history"] else None

    _save_trace(trace)
    client.close()


def _save_trace(trace: dict) -> None:
    activity_id = trace.get("activity_id") or "no_activity_id"
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(activity_id))
    out_dir = PROJECT_ROOT / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"heat_intelligence_documented_{safe_id}.json"
    out_path = out_dir / filename

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, default=str)

    print(f"\nExecution trace saved: {out_path}")
    print(f"  File size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
