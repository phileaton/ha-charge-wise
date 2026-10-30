"""Tests for the EV-first forecast calculation."""

from custom_components.charge_wise.utils.ev_first import EvFirstConfig, EvFirstInputs, evaluate_ev_first

CONFIG = EvFirstConfig(battery_capacity_kwh=27, battery_target_percent=90, forecast_trust_percent=80)


def _inputs(**overrides: float | None) -> EvFirstInputs:
    values: dict[str, float | None] = {
        "forecast_remaining_kwh": 30,
        "battery_level_percent": 50,
        "house_power_w": 500,
        "hours_until_sunset": 6,
    }
    values.update(overrides)
    return EvFirstInputs(**values)


def test_surplus_covering_the_battery_need_is_active() -> None:
    """30 kWh at 80% minus 3 kWh of house use covers the 10.8 kWh the battery still needs."""
    result = evaluate_ev_first(CONFIG, _inputs())

    assert result is not None
    assert round(result.battery_need_kwh, 2) == 10.8
    assert round(result.forecast_surplus_kwh, 2) == 21
    assert result.active


def test_surplus_below_the_battery_need_is_inactive() -> None:
    """A weak forecast leaves the battery first."""
    result = evaluate_ev_first(CONFIG, _inputs(forecast_remaining_kwh=10))

    assert result is not None
    assert not result.active


def test_battery_above_target_needs_nothing() -> None:
    """A full battery has no need, so any non-negative surplus is enough."""
    result = evaluate_ev_first(CONFIG, _inputs(battery_level_percent=95, forecast_remaining_kwh=5))

    assert result is not None
    assert result.battery_need_kwh == 0
    assert result.active


def test_missing_input_or_set_sun_returns_none() -> None:
    """Any unavailable input, or no daylight left, disables EV-first."""
    for field in ("forecast_remaining_kwh", "battery_level_percent", "house_power_w", "hours_until_sunset"):
        assert evaluate_ev_first(CONFIG, _inputs(**{field: None})) is None
    assert evaluate_ev_first(CONFIG, _inputs(hours_until_sunset=0)) is None
