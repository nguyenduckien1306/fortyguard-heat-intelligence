"""User-friendly error classification and messaging utilities.

Translates backend and transport errors into clean, categorized user messages
without exposing stack traces, headers, or internal credentials.
"""

from __future__ import annotations

from typing import NamedTuple


class ClassifiedError(NamedTuple):
    category: str
    message: str
    action_hint: str
    icon: str


def classify_user_error(error_msg: str, status_code: int | None = None) -> ClassifiedError:
    """Classify an error message into a user-friendly category and suggested action."""
    msg_lower = error_msg.lower()

    if status_code == 410 or "expired" in msg_lower:
        return ClassifiedError(
            category="Report Expired",
            message="The temporary download link for this report has expired.",
            action_hint="Please submit a new analysis to generate a fresh report.",
            icon="⌛",
        )

    if status_code == 401 or "api key" in msg_lower or "unauthorized" in msg_lower or "authentication" in msg_lower:
        return ClassifiedError(
            category="Authentication Error",
            message="The analysis service rejected the request credentials.",
            action_hint="Check server environment configuration.",
            icon="🔑",
        )

    if status_code == 404 or "not found" in msg_lower:
        return ClassifiedError(
            category="Resource Not Found",
            message="The requested task or endpoint was not found on FortyGuard.",
            action_hint="Verify the activity ID or endpoint configuration.",
            icon="🔍",
        )

    if status_code == 429 or "rate limit" in msg_lower:
        return ClassifiedError(
            category="Rate Limited",
            message="FortyGuard API rate limit was exceeded.",
            action_hint="Please wait a moment before trying again.",
            icon="⏱️",
        )

    if (
        "reach the fastapi backend" in msg_lower
        or "unable to reach" in msg_lower
        or "connection" in msg_lower
        or "connect" in msg_lower
        or "transport" in msg_lower
    ):
        return ClassifiedError(
            category="Network Error",
            message="The application could not reach the analysis service.",
            action_hint="Ensure the backend server and network are available.",
            icon="📡",
        )

    if "malformed" in msg_lower or "unexpected response" in msg_lower or "non-json" in msg_lower:
        return ClassifiedError(
            category="Invalid Response",
            message="The analysis service returned an unexpected response.",
            action_hint="Please try again or contact support if the issue persists.",
            icon="⚠️",
        )

    if status_code == 409 or "still processing" in msg_lower or "not ready" in msg_lower:
        return ClassifiedError(
            category="Processing",
            message="The analysis is still processing on FortyGuard.",
            action_hint="Poll again in a few moments.",
            icon="⏳",
        )

    if "timeout" in msg_lower or "timed out" in msg_lower:
        return ClassifiedError(
            category="Observation Timeout",
            message="The observation window elapsed while the analysis was still processing.",
            action_hint="Use 'Check Again' to resume checking status.",
            icon="⏱️",
        )

    if "validation" in msg_lower or status_code == 422:
        return ClassifiedError(
            category="Validation Error",
            message=error_msg,
            action_hint="Check that all required parameters are correctly formatted.",
            icon="⚠️",
        )

    return ClassifiedError(
        category="Provider Error",
        message=error_msg if len(error_msg) < 150 else "FortyGuard reported that the analysis failed, but did not provide a specific failure reason.",
        action_hint="Please verify parameters or try again later.",
        icon="⚠️",
    )
