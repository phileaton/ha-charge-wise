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
