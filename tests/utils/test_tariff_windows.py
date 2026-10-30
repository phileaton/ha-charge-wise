"""Unit tests for off-peak window calculations."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from custom_components.charge_wise.utils.tariff_windows import (
    TariffWindow,
    WindowDays,
    is_active,
    next_change,
    next_start,
)

LA = ZoneInfo("America/Los_Angeles")
NIGHT = TariffWindow(time(0, 0), time(6, 0))
EVENING = TariffWindow(time(22, 0), time(2, 0))


def test_same_day_window_boundaries() -> None:
    """A window is active from its start up to, but excluding, its end."""
    assert is_active([NIGHT], datetime(2026, 3, 4, 0, 0, tzinfo=LA))
    assert is_active([NIGHT], datetime(2026, 3, 4, 5, 59, tzinfo=LA))
    assert not is_active([NIGHT], datetime(2026, 3, 4, 6, 0, tzinfo=LA))


def test_window_crossing_midnight_stays_active_after_midnight() -> None:
    """The part after midnight belongs to the window that started the day before."""
    assert is_active([EVENING], datetime(2026, 3, 4, 23, 0, tzinfo=LA))
    assert is_active([EVENING], datetime(2026, 3, 5, 1, 30, tzinfo=LA))
    assert not is_active([EVENING], datetime(2026, 3, 5, 2, 0, tzinfo=LA))


def test_weekday_and_weekend_windows() -> None:
    """Days apply to the day the window starts."""
    weekend = TariffWindow(time(10, 0), time(14, 0), WindowDays.WEEKENDS)
    saturday = datetime(2026, 3, 7, 11, 0, tzinfo=LA)
    monday = datetime(2026, 3, 9, 11, 0, tzinfo=LA)

    assert is_active([weekend], saturday)
    assert not is_active([weekend], monday)
    friday_night = TariffWindow(time(22, 0), time(2, 0), WindowDays.WEEKDAYS)
    assert is_active([friday_night], datetime(2026, 3, 7, 1, 0, tzinfo=LA))
    assert not is_active([friday_night], datetime(2026, 3, 8, 1, 0, tzinfo=LA))


def test_next_change_and_next_start_are_utc_and_in_the_future() -> None:
    """Boundaries are returned in UTC so the coordinator can schedule timers."""
    now = datetime(2026, 3, 4, 3, 0, tzinfo=LA)

    assert next_change([NIGHT], now) == datetime(2026, 3, 4, 6, 0, tzinfo=LA).astimezone(UTC)
    assert next_start([NIGHT], now) == datetime(2026, 3, 5, 0, 0, tzinfo=LA).astimezone(UTC)


def test_no_windows_and_degenerate_windows_never_activate() -> None:
    """Empty or zero-length windows are ignored."""
    now = datetime(2026, 3, 4, 3, 0, tzinfo=LA)

    assert not is_active([], now)
    assert next_change([], now) is None
    assert next_start([TariffWindow(time(3, 0), time(3, 0))], now) is None


def test_dst_spring_forward_keeps_the_window_end_in_wall_clock_time() -> None:
    """On the spring-forward night the window still ends at 06:00 local time."""
    now = datetime(2026, 3, 8, 1, 0, tzinfo=LA)

    assert next_change([NIGHT], now) == datetime(2026, 3, 8, 6, 0, tzinfo=LA).astimezone(UTC)
