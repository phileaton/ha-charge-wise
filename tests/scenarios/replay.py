"""Replay exported days through the real controller, EV-first, forecast accuracy and house load logic.

The charger is simulated: it draws the requested current instantly while enabled. The recorded charger draw is
removed from the recorded grid power and the simulated draw is added back, while the battery and solar readings
stay as recorded. That makes a replay good for checking decision logic and comparing settings on the same days,
not for predicting absolute energy figures.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from custom_components.charge_wise.utils.charging_controller import (
    ChargeWiseController,
    ChargeWiseReason,
    ControllerConfig,
    ControllerInput,
    ControlSettings,
)
from custom_components.charge_wise.utils.ev_first import EvFirstConfig, EvFirstInputs, evaluate_ev_first
from custom_components.charge_wise.utils.forecast_accuracy import ForecastAccuracy
from custom_components.charge_wise.utils.house_load import HouseLoadProfile

DATA_DIR = Path(__file__).parent / "data"
STEP_S = 30
HARDWARE_MAXIMUM_A = 40.0

INSTALL_CONTROLLER = ControllerConfig(
    minimum_current_a=6,
    maximum_current_a=40,
    voltage_v=240,
    solar_start_w=1600,
    low_solar_confirmation_s=90,
    cooldown_s=90,
    battery_recovery_w=0,
    battery_recovery_confirmation_s=60,
    smoothing_window_s=60,
    settle_hold_s=30,
    current_deadband_a=1.0,
)
INSTALL_EV_FIRST = EvFirstConfig(battery_capacity_kwh=27, battery_target_percent=100, release_margin_percent=25)


@dataclass
class DayResult:
    """What the controller did on one replayed day."""

    date: str
    starts: int = 0
    stops: int = 0
    ev_kwh: float = 0.0
    ev_grid_kwh: float = 0.0
    charging_minutes: float = 0.0
    ev_first_minutes: float = 0.0
    solar_kwh: float = 0.0
    longest_pause_min_with_budget: float = 0.0
    timeline: list[tuple[str, str, str, bool, float]] = field(default_factory=list)


class Series:
    """A step-held time series of [seconds, value] points."""

    def __init__(self, points: Sequence[Sequence[float]]) -> None:
        """Index the points for lookup."""
        self._times = [point[0] for point in points]
        self._values = [point[1] for point in points]

    def at(self, seconds: float) -> float | None:
        """Return the value held at the given time, or None before the first reading."""
        index = bisect_right(self._times, seconds) - 1
        return self._values[index] if index >= 0 else None


def load_day(name: str) -> dict:
    """Load a fixture by date, for example '2026-11-03'."""
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def available_days() -> list[str]:
    """Return the dates of every stored fixture in order."""
    return sorted(path.stem for path in DATA_DIR.glob("*.json"))


def replay(
    days: Sequence[str],
    *,
    controller_config: ControllerConfig = INSTALL_CONTROLLER,
    ev_first_config: EvFirstConfig | None = INSTALL_EV_FIRST,
    house_window_days: float = 3,
) -> list[DayResult]:
    """Replay the days in order, carrying the learned house load profile from one day to the next."""
    profile = HouseLoadProfile(house_window_days)
    return [_replay_day(load_day(name), controller_config, ev_first_config, profile) for name in days]


def _replay_day(
    day: dict,
    controller_config: ControllerConfig,
    ev_first_config: EvFirstConfig | None,
    profile: HouseLoadProfile,
) -> DayResult:
    zone = ZoneInfo(day["timezone"])
    start = datetime.fromisoformat(day["start_utc"]).astimezone(zone)
    sunset = start + timedelta(seconds=day["sunset_s"])
    series = {key: Series(points) for key, points in day["series"].items()}
    controller = ChargeWiseController(controller_config)
    accuracy = ForecastAccuracy()
    settings = ControlSettings(enabled=True, solar_enabled=True)
    result = DayResult(date=day["date"])

    charger_enabled = False
    current_a = float(controller_config.minimum_current_a)
    ev_first_active = False
    last_key: tuple[str, str, bool, float] | None = None
    paused_with_budget_s = 0.0

    for offset in range(0, day["seconds"], STEP_S):
        now = start + timedelta(seconds=offset)
        solar = series["solar_w"].at(offset)
        grid = series["grid_w"].at(offset)
        battery_discharge = series["battery_w"].at(offset)
        level = series["battery_level"].at(offset)
        forecast_remaining = series["forecast_remaining_kwh"].at(offset)
        forecast_today = series["forecast_today_kwh"].at(offset)
        recorded_charger = series["charger_w"].at(offset) if "charger_w" in series else None
        if solar is None or grid is None or battery_discharge is None:
            continue

        charger_w = current_a * controller_config.voltage_v if charger_enabled else 0.0
        grid_without_ev = grid - (recorded_charger or 0.0)
        simulated_grid = grid_without_ev + charger_w
        house_w = max(0.0, solar + grid_without_ev + battery_discharge)

        profile.observe(house_w, now)
        if forecast_today is not None and forecast_remaining is not None:
            accuracy.observe(now, solar, max(0.0, forecast_today - forecast_remaining))
        else:
            accuracy.observe(now, solar, None)

        if ev_first_config is not None:
            hours_left = (sunset - now).total_seconds() / 3600
            evaluation = evaluate_ev_first(
                ev_first_config,
                EvFirstInputs(
                    forecast_remaining_kwh=forecast_remaining,
                    battery_level_percent=level,
                    house_use_kwh=profile.expected_energy_kwh(now, sunset, house_w) if hours_left > 0 else None,
                    hours_until_sunset=hours_left,
                    forecast_accuracy=accuracy.ratio if accuracy.ratio is not None else 1.0,
                ),
                was_active=ev_first_active,
            )
            ev_first_active = evaluation is not None and evaluation.active

        decision = controller.evaluate(
            settings,
            ControllerInput(
                grid_power_w=simulated_grid,
                charger_power_w=charger_w,
                battery_discharge_w=battery_discharge,
                battery_configured=True,
                ev_connected=None,
                ev_connected_configured=False,
                charger_enabled=charger_enabled,
                current_target_a=current_a,
                hardware_maximum_a=HARDWARE_MAXIMUM_A,
                ev_first_boost_w=max(0.0, -battery_discharge) if ev_first_active else 0.0,
                ev_first_blocked=ev_first_config is not None and not ev_first_active,
            ),
            now,
        )

        if decision.charger_enabled and not charger_enabled:
            result.starts += 1
        elif charger_enabled and not decision.charger_enabled:
            result.stops += 1
        charger_enabled = decision.charger_enabled
        if charger_enabled:
            current_a = decision.requested_current_a

        seconds = float(STEP_S)
        result.solar_kwh += solar * seconds / 3_600_000
        if charger_enabled:
            result.charging_minutes += seconds / 60
            result.ev_kwh += current_a * controller_config.voltage_v * seconds / 3_600_000
            result.ev_grid_kwh += min(charger_w, max(0.0, simulated_grid)) * seconds / 3_600_000
            paused_with_budget_s = 0.0
        elif (
            decision.reason is not ChargeWiseReason.EV_FIRST_WAITING
            and (decision.available_solar_w or 0) >= controller_config.solar_start_w
        ):
            paused_with_budget_s += seconds
            result.longest_pause_min_with_budget = max(result.longest_pause_min_with_budget, paused_with_budget_s / 60)
        else:
            paused_with_budget_s = 0.0
        if ev_first_active:
            result.ev_first_minutes += seconds / 60

        key = (decision.status.value, decision.reason.value, charger_enabled, round(current_a))
        if key != last_key:
            result.timeline.append((now.strftime("%H:%M:%S"), *key))
            last_key = key

    return result


def summary(results: Sequence[DayResult]) -> str:
    """Return one line per day, for printing while tuning."""
    lines = ["date        starts stops ev_kWh  charging_min  ev_first_min  solar_kWh  max_pause_with_budget_min"]
    lines.extend(
        f"{item.date}  {item.starts:5d} {item.stops:5d} {item.ev_kwh:7.1f} {item.charging_minutes:12.0f}"
        f" {item.ev_first_minutes:13.0f} {item.solar_kwh:10.1f} {item.longest_pause_min_with_budget:12.0f}"
        for item in results
    )
    return "\n".join(lines)


def with_margin(config: EvFirstConfig, margin_percent: float) -> EvFirstConfig:
    """Return the EV-first config with a different release margin, for settings comparisons."""
    return replace(config, release_margin_percent=margin_percent)


if __name__ == "__main__":
    print(summary(replay(available_days())))  # noqa: T201
