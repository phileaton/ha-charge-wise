"""Pure forecast calculation that decides whether the EV may share the battery's charging power."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvFirstConfig:
    """Battery and forecast settings used to size the battery's need."""

    battery_capacity_kwh: float
    battery_target_percent: float = 90
    forecast_trust_percent: float = 80


@dataclass(frozen=True)
class EvFirstInputs:
    """Readings needed for the calculation; any missing reading disables EV-first."""

    forecast_remaining_kwh: float | None
    battery_level_percent: float | None
    house_power_w: float | None
    hours_until_sunset: float | None


@dataclass(frozen=True)
class EvFirstResult:
    """Energy balance for the rest of the solar day."""

    battery_need_kwh: float
    forecast_surplus_kwh: float

    @property
    def active(self) -> bool:
        """Return whether the trusted forecast covers the battery's remaining need."""
        return self.forecast_surplus_kwh >= self.battery_need_kwh


def evaluate_ev_first(config: EvFirstConfig, inputs: EvFirstInputs) -> EvFirstResult | None:
    """Return the energy balance, or None while any input is unavailable or the sun is down."""
    if (
        inputs.forecast_remaining_kwh is None
        or inputs.battery_level_percent is None
        or inputs.house_power_w is None
        or inputs.hours_until_sunset is None
        or inputs.hours_until_sunset <= 0
    ):
        return None

    missing_percent = max(0.0, config.battery_target_percent - inputs.battery_level_percent)
    battery_need_kwh = missing_percent / 100 * config.battery_capacity_kwh
    trusted_forecast_kwh = max(0.0, inputs.forecast_remaining_kwh) * config.forecast_trust_percent / 100
    house_use_kwh = max(0.0, inputs.house_power_w) * inputs.hours_until_sunset / 1000
    return EvFirstResult(battery_need_kwh, trusted_forecast_kwh - house_use_kwh)
