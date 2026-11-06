"""Scenario tests: recorded days replayed through the real decision logic."""

import pytest

from .replay import INSTALL_EV_FIRST, DayResult, available_days, load_day, replay, summary, with_margin  # noqa: TID251

DAYS = available_days()
pytestmark = pytest.mark.skipif(not DAYS, reason="no scenario fixtures exported")


@pytest.fixture(scope="module")
def results() -> list[DayResult]:
    """Replay every stored day in order, as the live install would have seen them."""
    return replay(DAYS)


def test_fixtures_are_well_formed() -> None:
    """Every fixture carries the series the replay needs, in time order."""
    for name in DAYS:
        day = load_day(name)
        assert day["sunrise_s"] < day["sunset_s"]
        for key in ("solar_w", "grid_w", "battery_w", "battery_level", "forecast_remaining_kwh", "forecast_today_kwh"):
            times = [point[0] for point in day["series"][key]]
            assert times == sorted(times), f"{name}:{key}"


def test_replay_is_deterministic(results: list[DayResult]) -> None:
    """The same inputs always produce the same decisions."""
    assert summary(replay(DAYS)) == summary(results)


def test_charging_never_idles_while_budget_is_available(results: list[DayResult]) -> None:
    """A paused charger with a start-sized budget resumes within the cooldown and confirmation window."""
    for item in results:
        assert item.longest_pause_min_with_budget <= 10, item.date


def test_no_flapping(results: list[DayResult]) -> None:
    """Starts and stops stay bounded and balanced on every recorded day."""
    for item in results:
        assert item.starts <= 20, item.date
        assert abs(item.starts - item.stops) <= 1, item.date


def test_energy_to_ev_never_exceeds_solar(results: list[DayResult]) -> None:
    """The EV can use at most what the panels made plus the battery's surplus, never more than the day's solar."""
    for item in results:
        assert item.ev_kwh <= item.solar_kwh, item.date


def test_longer_restart_margin_does_not_increase_sharing_time() -> None:
    """A larger restart surplus buffer does not increase sharing on the recorded days."""
    tight = replay(DAYS, ev_first_config=with_margin(INSTALL_EV_FIRST, 5))
    loose = replay(DAYS, ev_first_config=with_margin(INSTALL_EV_FIRST, 40))
    for narrow, wide in zip(tight, loose, strict=True):
        assert wide.ev_first_minutes <= narrow.ev_first_minutes, narrow.date
