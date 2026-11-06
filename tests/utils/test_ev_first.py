"""Tests for the EV-first forecast calculation."""

from custom_components.charge_wise.utils.ev_first import EvFirstConfig, EvFirstInputs, evaluate_ev_first

CONFIG = EvFirstConfig(battery_capacity_kwh=27, battery_target_percent=90)


def _inputs(**overrides: float | None) -> EvFirstInputs:
    values: dict[str, float | None] = {
        "forecast_remaining_kwh": 30,
        "battery_level_percent": 50,
        "house_use_kwh": 3,
        "hours_until_sunset": 6,
        "forecast_accuracy": 0.8,
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


def test_active_state_stops_as_soon_as_battery_coverage_is_short() -> None:
    """A short forecast stops sharing even if it was already active."""
    inputs = _inputs(forecast_remaining_kwh=17)

    started = evaluate_ev_first(CONFIG, inputs)
    held = evaluate_ev_first(CONFIG, inputs, was_active=True)

    assert started is not None
    assert held is not None
    assert not started.active
    assert not held.active


def test_active_state_releases_below_the_margin() -> None:
    """A surplus of 6.6 kWh is more than 25% under the 10.8 kWh need, so it releases."""
    result = evaluate_ev_first(CONFIG, _inputs(forecast_remaining_kwh=12), was_active=True)

    assert result is not None
    assert not result.active


def test_zero_margin_releases_as_soon_as_the_surplus_is_short() -> None:
    """With no margin the held state gives no extra room."""
    config = EvFirstConfig(battery_capacity_kwh=27, release_margin_percent=0)

    result = evaluate_ev_first(config, _inputs(forecast_remaining_kwh=17), was_active=True)

    assert result is not None
    assert not result.active


def test_missing_input_or_set_sun_returns_none() -> None:
    """Any unavailable input, or no daylight left, disables EV-first."""
    for field in ("forecast_remaining_kwh", "battery_level_percent", "house_use_kwh", "hours_until_sunset"):
        assert evaluate_ev_first(CONFIG, _inputs(**{field: None})) is None
    assert evaluate_ev_first(CONFIG, _inputs(hours_until_sunset=0)) is None


def test_battery_reserve_uses_remaining_need_and_daylight() -> None:
    """The battery reserve is the average power required to reach its target by sunset."""
    result = evaluate_ev_first(CONFIG, _inputs(hours_until_sunset=3, forecast_remaining_kwh=5))
    assert result is not None
    assert not result.active
    assert result.battery_reserve_w == 3600


def test_exact_battery_coverage_stops_sharing() -> None:
    """Equality is a stop, even for an active session with a configured margin."""
    result = evaluate_ev_first(
        CONFIG, _inputs(forecast_remaining_kwh=10.8, forecast_accuracy=1, house_use_kwh=0), was_active=True
    )
    assert result is not None
    assert result.forecast_surplus_kwh == result.battery_need_kwh
    assert not result.active


def test_restart_margin_is_above_the_battery_need() -> None:
    """Surplus inside the restart buffer holds an active session but cannot begin a new one."""
    inputs = _inputs(forecast_remaining_kwh=12, forecast_accuracy=1, house_use_kwh=0)
    running = evaluate_ev_first(CONFIG, inputs, was_active=True)
    restarting = evaluate_ev_first(CONFIG, inputs)
    assert running is not None and running.active
    assert restarting is not None and not restarting.active


def test_full_battery_releases_forecast_priority() -> None:
    """A full battery permits solar charging even with zero or negative forecast surplus."""
    for forecast in (0, 3):
        for was_active in (False, True):
            result = evaluate_ev_first(
                CONFIG,
                _inputs(battery_level_percent=100, forecast_remaining_kwh=forecast, forecast_accuracy=1),
                was_active=was_active,
            )
            assert result is not None
            assert result.active
            assert result.battery_need_kwh == 0
            assert result.battery_reserve_w == 0


def test_battery_below_full_retains_forecast_priority() -> None:
    """Dropping below full restores battery priority when the forecast is short."""
    result = evaluate_ev_first(CONFIG, _inputs(battery_level_percent=99, forecast_remaining_kwh=0))
    assert result is not None
    assert not result.active
