"""Tests for the measured forecast accuracy."""

from datetime import UTC, datetime, timedelta

from custom_components.charge_wise.utils.forecast_accuracy import ForecastAccuracy

START = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


def _run(tracker: ForecastAccuracy, minutes: int, solar_w: float, forecast_start: float, forecast_end: float) -> None:
    for step in range(minutes + 1):
        now = START + timedelta(minutes=step)
        forecast = forecast_start + (forecast_end - forecast_start) * step / minutes
        tracker.observe(now, solar_w, forecast)


def test_ratio_is_unknown_until_enough_forecast_has_passed() -> None:
    """A morning sliver of forecast says nothing about the rest of the day."""
    tracker = ForecastAccuracy()
    _run(tracker, 10, 2000, 0.0, 1.0)

    assert tracker.ratio is None


def test_ratio_compares_production_with_the_forecast_for_the_same_period() -> None:
    """4 kW for an hour is 4 kWh against 5 kWh forecast, so 80%."""
    tracker = ForecastAccuracy()
    _run(tracker, 60, 4000, 1.0, 6.0)

    assert tracker.ratio is not None
    assert round(tracker.ratio, 2) == 0.8


def test_ratio_is_clamped() -> None:
    """A near-zero or huge reading cannot swing the forecast beyond the limits."""
    low = ForecastAccuracy()
    _run(low, 60, 0, 0.0, 5.0)
    high = ForecastAccuracy()
    _run(high, 60, 20000, 0.0, 5.0)

    assert low.ratio == 0.3
    assert high.ratio == 1.2


def test_a_new_day_starts_over() -> None:
    """Yesterday's measurement is discarded."""
    tracker = ForecastAccuracy()
    _run(tracker, 60, 4000, 0.0, 5.0)

    tracker.observe(START + timedelta(days=1), 4000, 0.0)

    assert tracker.ratio is None
    assert tracker.actual_kwh == 0.0


def test_state_round_trips_only_within_the_same_day() -> None:
    """A restart keeps today's measurement but not an older one."""
    tracker = ForecastAccuracy()
    _run(tracker, 60, 4000, 0.0, 5.0)
    saved = tracker.as_dict()

    same_day = ForecastAccuracy()
    same_day.restore(saved, START.date())
    next_day = ForecastAccuracy()
    next_day.restore(saved, START.date() + timedelta(days=1))

    assert same_day.ratio == tracker.ratio
    assert next_day.ratio is None


def test_downtime_is_left_out_of_the_comparison() -> None:
    """Forecast that passed while Home Assistant was down must not count against the panels."""
    tracker = ForecastAccuracy()
    _run(tracker, 60, 4000, 0.0, 4.0)
    saved = tracker.as_dict()

    restarted = ForecastAccuracy()
    restarted.restore(saved, START.date())
    resume = START + timedelta(hours=3)
    restarted.observe(resume, 4000, 10.0)
    for step in range(1, 61):
        restarted.observe(resume + timedelta(minutes=step), 4000, 10.0 + 4.0 * step / 60)

    assert restarted.ratio is not None
    assert round(restarted.ratio, 2) == 1.0
    assert round(restarted.tracked_forecast_kwh, 1) == 8.0


def test_a_downward_forecast_revision_restarts_the_measurement() -> None:
    """When the forecast so far drops, the old comparison is meaningless and starts over."""
    tracker = ForecastAccuracy()
    _run(tracker, 60, 4000, 8.0, 12.0)

    tracker.observe(START + timedelta(minutes=61), 4000, 7.0)

    assert tracker.baseline_forecast_kwh == 7.0
    assert tracker.actual_kwh < 0.1
    assert tracker.ratio is None


def test_restore_discards_state_whose_forecast_is_behind_its_baseline() -> None:
    """Saved production without matching forecast progress would inflate the ratio, so it is dropped."""
    tracker = ForecastAccuracy()
    tracker.restore(
        {"day": START.date().isoformat(), "baseline_forecast_kwh": 8.5, "latest_forecast_kwh": 6.7, "actual_kwh": 6.7},
        START.date(),
    )

    assert tracker.baseline_forecast_kwh is None
    assert tracker.actual_kwh == 0.0


def test_energy_counter_replaces_power_integration() -> None:
    """With an energy counter, production is the counter's growth and the power reading is ignored."""
    tracker = ForecastAccuracy()
    for step in range(61):
        tracker.observe(START + timedelta(minutes=step), 9999, 4.0 * step / 60, 100.0 + 3.0 * step / 60)

    assert tracker.actual_kwh == 3.0
    assert tracker.ratio == 0.75


def test_anchoring_to_midnight_counts_the_whole_day_so_far() -> None:
    """A midnight counter value makes the comparison cover everything since midnight, not since startup."""
    tracker = ForecastAccuracy()
    tracker.anchor_to_day_start(START.date(), 100.0)

    tracker.observe(START, None, 6.0, 105.0)

    assert tracker.tracked_forecast_kwh == 6.0
    assert tracker.ratio is not None
    assert round(tracker.ratio, 3) == 0.833


def test_counter_downtime_does_not_lose_production() -> None:
    """The counter keeps counting while Home Assistant is down, and the forecast baseline stays put."""
    tracker = ForecastAccuracy()
    tracker.anchor_to_day_start(START.date(), 100.0)
    tracker.observe(START, None, 2.0, 102.0)
    saved = tracker.as_dict()

    restarted = ForecastAccuracy()
    restarted.restore(saved, START.date(), energy_counter=True)
    restarted.observe(START + timedelta(hours=3), None, 8.0, 108.0)

    assert restarted.ratio == 1.0


def test_a_counter_reset_restarts_the_comparison() -> None:
    """A counter that drops has been reset or replaced, so earlier readings no longer apply."""
    tracker = ForecastAccuracy()
    tracker.anchor_to_day_start(START.date(), 500.0)
    tracker.observe(START, None, 4.0, 504.0)

    tracker.observe(START + timedelta(minutes=5), None, 4.5, 0.2)

    assert tracker.baseline_energy_kwh == 0.2
    assert tracker.baseline_forecast_kwh == 4.5
    assert tracker.actual_kwh == 0.0


def test_restore_drops_state_from_a_different_production_source() -> None:
    """Switching between the power sensor and the energy counter starts the comparison over."""
    power = ForecastAccuracy()
    _run(power, 30, 4000, 0.0, 2.0)

    switched = ForecastAccuracy()
    switched.restore(power.as_dict(), START.date(), energy_counter=True)

    assert switched.baseline_forecast_kwh is None
