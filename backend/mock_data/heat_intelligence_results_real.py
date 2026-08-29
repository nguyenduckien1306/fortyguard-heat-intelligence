"""Confirmed real response schema fixture from FortyGuard Heat Intelligence live discovery.

Discovered from live capture:
- Submission Endpoint: POST /v1/heat_intelligence
- Activity ID: 914beca8-754b-4353-9bff-23b9ef055a66
- Polling: 28 attempts (~116.9s) -> Completed
- Completed Result Schema:
  {"download_link": "https://..."}

Note: Credentials and sensitive query parameters in the signed download link have been sanitized for tests.
"""

from __future__ import annotations

from typing import Any

# Confirmed real schema observed from FortyGuard completed task
REAL_CONFIRMED_HEAT_INTELLIGENCE_RESULT: dict[str, Any] = {
    "download_link": "https://tos-dashboard-prod.s3.amazonaws.com/enterprise_api/activity_id%3D914beca8-754b-4353-9bff-23b9ef055a66/data.pdf?X-Amz-Signature=SANITIZED"
}

# Historical 404 response observed when calling the unmapped hyphenated endpoint
REAL_OBSERVED_404_RESPONSE: dict[str, Any] = {
    "error": True,
    "status_code": 404,
    "details": {
        "message": "Endpoint not found",
    },
}
