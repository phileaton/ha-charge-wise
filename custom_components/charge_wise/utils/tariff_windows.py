"""Pure off-peak time window calculations for Charge Wise."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

_WEEKEND_START = 5


class WindowDays(StrEnum):
    """Days a window applies to, counted from the day the window starts."""

    ALL = "all"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"


@dataclass(frozen=True)
class TariffWindow:
    """A daily window that may cross midnight."""

    start: time
    end: time
    days: WindowDays = WindowDays.ALL

    def applies_on(self, day: date) -> bool:
        """Return whether the window may start on the given date."""
        if self.days is WindowDays.ALL:
            return True
        is_weekend = day.weekday() >= _WEEKEND_START
        return is_weekend if self.days is WindowDays.WEEKENDS else not is_weekend


def windows_from_options(raw: object) -> list[TariffWindow]:
    """Parse stored window options, skipping entries that are malformed."""
    if not isinstance(raw, list):
        return []
    windows: list[TariffWindow] = []
    for item in raw:
        try:
            windows.append(
                TariffWindow(
                    start=time.fromisoformat(item["start"]),
                    end=time.fromisoformat(item["end"]),
                    days=WindowDays(item.get("days", WindowDays.ALL)),
                ),
            )
        except KeyError, TypeError, ValueError:
            continue
    return windows


def _intervals(windows: Sequence[TariffWindow], now: datetime) -> list[tuple[datetime, datetime]]:
    """Expand windows into UTC intervals around now, in now's time zone."""
    today = now.date()
    intervals: list[tuple[datetime, datetime]] = []
    for offset in range(-1, 9):
        day = today + timedelta(days=offset)
        for window in windows:
            if window.start == window.end or not window.applies_on(day):
                continue
            end_day = day + timedelta(days=1) if window.end < window.start else day
            start_at = datetime.combine(day, window.start, tzinfo=now.tzinfo).astimezone(UTC)
            end_at = datetime.combine(end_day, window.end, tzinfo=now.tzinfo).astimezone(UTC)
            intervals.append((start_at, end_at))
    return intervals


def is_active(windows: Sequence[TariffWindow], now: datetime) -> bool:
    """Return whether now falls inside any window."""
    return any(start <= now < end for start, end in _intervals(windows, now))


def next_change(windows: Sequence[TariffWindow], now: datetime) -> datetime | None:
    """Return the next UTC time a window starts or ends."""
    boundaries = [moment for interval in _intervals(windows, now) for moment in interval if moment > now]
    return min(boundaries) if boundaries else None


def next_start(windows: Sequence[TariffWindow], now: datetime) -> datetime | None:
    """Return the next UTC time a window starts."""
    starts = [start for start, _ in _intervals(windows, now) if start > now]
    return min(starts) if starts else None
