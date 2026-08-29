"""FortyGuard API client exceptions."""


class FortyGuardClientError(Exception):
    """Base exception for FortyGuard client errors."""

    http_status: int = 500

    def __init__(self, message: str, http_status: int | None = None) -> None:
        super().__init__(message)
        if http_status is not None:
            self.http_status = http_status


class InvalidRequestError(FortyGuardClientError):
    """Raised for HTTP 400/422 invalid request responses."""

    http_status = 422


class AuthenticationError(FortyGuardClientError):
    """Raised for HTTP 401 missing or invalid API key."""

    http_status = 401


class ForbiddenError(FortyGuardClientError):
    """Raised for HTTP 403 insufficient plan access."""

    http_status = 403


class NotFoundError(FortyGuardClientError):
    """Raised for HTTP 404 activity not found or temporarily unavailable."""

    http_status = 404


class RateLimitError(FortyGuardClientError):
    """Raised for HTTP 429 rate limit responses."""

    http_status = 429


class ServerError(FortyGuardClientError):
    """Raised for HTTP 500 server-side processing errors."""

    http_status = 500


class TransportError(FortyGuardClientError):
    """Raised when the FortyGuard HTTP request cannot be completed."""

    http_status = 502


class MalformedResponseError(FortyGuardClientError):
    """Raised when a successful HTTP response has an invalid payload."""

    http_status = 502


class PollingTimeoutError(FortyGuardClientError):
    """Raised when polling exceeds the configured attempt limit."""

    http_status = 504

    def __init__(
        self,
        message: str,
        activity_id: str,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message, http_status=http_status)
        self.activity_id = activity_id
