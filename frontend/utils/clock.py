"""Injectable Clock Abstraction for Deterministic Temporal Operations.

Enables pure, deterministic unit testing of time-sensitive operations:
- Watchlist timestamps and evaluation freshness
- Signal created_at timestamps
- Alert cooldown windows and expiration
- Priority recency decay scoring
- Investigation notes and audit trail timestamps
- Snapshot generation timestamps
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 timestamps, including trailing Z UTC designators."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


class Clock(ABC):
    """Abstract Clock interface."""

    @abstractmethod
    def now(self) -> datetime:
        """Return current datetime snapshot."""
        ...

    def now_iso(self) -> str:
        """Return current datetime as ISO-8601 string."""
        return self.now().isoformat()

    def timestamp(self) -> float:
        """Return current POSIX timestamp."""
        return self.now().timestamp()


class SystemClock(Clock):
    """Production clock using real system wall-clock time."""

    def now(self) -> datetime:
        return datetime.now()


class FrozenClock(Clock):
    """Immutable clock fixed at a specific instant."""

    def __init__(self, frozen_time: datetime | str | None = None) -> None:
        if frozen_time is None:
            self._time = datetime(2026, 8, 23, 10, 0, 0)
        elif isinstance(frozen_time, str):
            self._time = _parse_iso_datetime(frozen_time)
        elif isinstance(frozen_time, datetime):
            self._time = frozen_time
        else:
            raise TypeError(f"Invalid frozen_time type: {type(frozen_time)}")

    def now(self) -> datetime:
        return self._time


class ManualClock(Clock):
    """Controllable clock supporting explicit time advancement."""

    def __init__(self, initial_time: datetime | str | None = None) -> None:
        if initial_time is None:
            self._time = datetime(2026, 8, 23, 10, 0, 0)
        elif isinstance(initial_time, str):
            self._time = _parse_iso_datetime(initial_time)
        elif isinstance(initial_time, datetime):
            self._time = initial_time
        else:
            raise TypeError(f"Invalid initial_time type: {type(initial_time)}")

    def now(self) -> datetime:
        return self._time

    def advance(self, seconds: float = 0, minutes: float = 0, hours: float = 0, days: float = 0) -> datetime:
        """Advance the clock by a specified duration."""
        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        self._time = self._time + delta
        return self._time

    def set_time(self, new_time: datetime | str) -> datetime:
        """Explicitly set the current clock time."""
        if isinstance(new_time, str):
            self._time = _parse_iso_datetime(new_time)
        elif isinstance(new_time, datetime):
            self._time = new_time
        else:
            raise TypeError(f"Invalid new_time type: {type(new_time)}")
        return self._time


# Global default clock instance (can be overridden in tests via set_current_clock)
_CURRENT_CLOCK: Clock = SystemClock()


def get_current_clock() -> Clock:
    """Retrieve the currently active clock instance."""
    global _CURRENT_CLOCK
    return _CURRENT_CLOCK


def set_current_clock(clock: Clock | None) -> Clock:
    """Set the globally active clock instance (pass None to reset to SystemClock)."""
    global _CURRENT_CLOCK
    if clock is None:
        _CURRENT_CLOCK = SystemClock()
    else:
        _CURRENT_CLOCK = clock
    return _CURRENT_CLOCK


def parse_timestamp_safe(ts_val: Any, default_time: datetime | None = None) -> datetime:
    """Safely parse various datetime/string/float inputs into a valid datetime."""
    if isinstance(ts_val, datetime):
        return ts_val
    if isinstance(ts_val, (int, float)):
        try:
            return datetime.fromtimestamp(ts_val)
        except (ValueError, OSError):
            pass
    if isinstance(ts_val, str) and ts_val.strip():
        try:
            return _parse_iso_datetime(ts_val.strip())
        except (ValueError, TypeError):
            # Try space-separated fallback
            try:
                return datetime.strptime(ts_val.strip()[:19], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass

    return default_time or datetime(2026, 8, 23, 0, 0, 0)


FrozenClock = FrozenClock
ManualClock = ManualClock
SystemClock = SystemClock
FrozenClock = FrozenClock
ManualClock = ManualClock
SystemClock = SystemClock
