"""Pure forecast calculation that decides whether the EV may share the battery's charging power."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvFirstConfig:
    """Battery and forecast settings used to size the battery's need."""

    battery_capacity_kwh: float
    battery_target_percent: float = 90
    release_margin_percent: float = 25


@dataclass(frozen=True)
class EvFirstInputs:
    """Readings needed for the calculation; any missing reading disables EV-first."""

    forecast_remaining_kwh: float | None
    battery_level_percent: float | None
    house_use_kwh: float | None
    hours_until_sunset: float | None
    forecast_accuracy: float = 1.0


@dataclass(frozen=True)
class EvFirstResult:
    """Energy balance for the rest of the solar day."""

    battery_need_kwh: float
    forecast_surplus_kwh: float
    active: bool
    battery_reserve_w: float = 0.0


def evaluate_ev_first(
    config: EvFirstConfig,
    inputs: EvFirstInputs,
    *,
    was_active: bool = False,
) -> EvFirstResult | None:
    """Return the energy balance, or None while any input is unavailable or the sun is down.

    forecast_accuracy is the measured share of the forecast that has actually materialised today (1.0 until known).

    Active sharing stops at full battery coverage; the margin applies only when starting again.
    """
    if (
        inputs.forecast_remaining_kwh is None
        or inputs.battery_level_percent is None
        or inputs.house_use_kwh is None
        or inputs.hours_until_sunset is None
        or inputs.hours_until_sunset <= 0
    ):
        return None

    missing_percent = max(0.0, config.battery_target_percent - inputs.battery_level_percent)
    battery_need_kwh = missing_percent / 100 * config.battery_capacity_kwh
    trusted_forecast_kwh = max(0.0, inputs.forecast_remaining_kwh) * inputs.forecast_accuracy
    house_use_kwh = max(0.0, inputs.house_use_kwh)
    surplus_kwh = trusted_forecast_kwh - house_use_kwh
    threshold_kwh = battery_need_kwh if was_active else battery_need_kwh * (1 + config.release_margin_percent / 100)
    return EvFirstResult(
        battery_need_kwh,
        surplus_kwh,
        inputs.battery_level_percent >= 100 or surplus_kwh > threshold_kwh,
        battery_need_kwh * 1000 / inputs.hours_until_sunset,
    )
