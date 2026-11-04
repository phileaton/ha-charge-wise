"""Measure how much of the solar forecast the panels actually delivered today."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

MIN_FORECAST_KWH = 2.0
MIN_RATIO = 0.3
MAX_RATIO = 1.2
MAX_ELAPSED_S = 300
REVISION_TOLERANCE_KWH = 0.05


@dataclass
class ForecastAccuracy:
    """Compare solar energy produced since tracking began with the energy forecast for the same period."""

    day: date | None = None
    baseline_forecast_kwh: float | None = None
    latest_forecast_kwh: float = 0.0
    actual_kwh: float = 0.0
    last_at: datetime | None = None
    baseline_energy_kwh: float | None = None
    latest_energy_kwh: float = 0.0

    def anchor_to_day_start(self, day: date, energy_kwh: float) -> None:
        """Start the day's comparison from an energy counter reading taken at local midnight."""
        self.day = day
        self.baseline_energy_kwh = self.latest_energy_kwh = energy_kwh
        self.baseline_forecast_kwh = 0.0
        self.latest_forecast_kwh = 0.0
        self.actual_kwh = 0.0
        self.last_at = None

    def observe(
        self,
        now: datetime,
        solar_w: float | None,
        forecast_so_far_kwh: float | None,
        solar_energy_kwh: float | None = None,
    ) -> None:
        """Record the forecast progress and the production, from the energy counter when there is one."""
        if self.day != now.date():
            self.day = now.date()
            self.baseline_forecast_kwh = None
            self.latest_forecast_kwh = 0.0
            self.actual_kwh = 0.0
            self.last_at = None
            self.baseline_energy_kwh = None
            self.latest_energy_kwh = 0.0
        last_at, self.last_at = self.last_at, now
        if solar_energy_kwh is not None:
            self._observe_energy(solar_energy_kwh, forecast_so_far_kwh)
            return
        if self.baseline_energy_kwh is not None or forecast_so_far_kwh is None:
            return
        if self.baseline_forecast_kwh is None:
            self.baseline_forecast_kwh = forecast_so_far_kwh
        elif forecast_so_far_kwh < self.latest_forecast_kwh - REVISION_TOLERANCE_KWH:
            self.baseline_forecast_kwh = forecast_so_far_kwh
            self.actual_kwh = 0.0
        elif last_at is None or (now - last_at).total_seconds() > MAX_ELAPSED_S:
            self.baseline_forecast_kwh += max(0.0, forecast_so_far_kwh - self.latest_forecast_kwh)
        self.latest_forecast_kwh = forecast_so_far_kwh
        if last_at is not None and solar_w is not None:
            elapsed_s = min((now - last_at).total_seconds(), MAX_ELAPSED_S)
            self.actual_kwh += max(0.0, solar_w) * max(0.0, elapsed_s) / 3_600_000

    def _observe_energy(self, energy_kwh: float, forecast_so_far_kwh: float | None) -> None:
        """Compare the energy counter's growth with the forecast's growth since the baseline."""
        if forecast_so_far_kwh is None:
            return
        if (
            self.baseline_energy_kwh is None
            or energy_kwh < self.latest_energy_kwh
            or forecast_so_far_kwh < self.latest_forecast_kwh - REVISION_TOLERANCE_KWH
        ):
            self.baseline_energy_kwh = energy_kwh
            self.baseline_forecast_kwh = forecast_so_far_kwh
        self.latest_energy_kwh = energy_kwh
        self.latest_forecast_kwh = forecast_so_far_kwh
        self.actual_kwh = energy_kwh - (self.baseline_energy_kwh or 0.0)

    @property
    def tracked_forecast_kwh(self) -> float:
        """Return the forecast energy that has passed while production was being measured."""
        if self.baseline_forecast_kwh is None:
            return 0.0
        return max(0.0, self.latest_forecast_kwh - self.baseline_forecast_kwh)

    @property
    def ratio(self) -> float | None:
        """Return actual ÷ forecast clamped to a sane range, or None until enough forecast energy has passed."""
        if self.baseline_forecast_kwh is None:
            return None
        forecast_kwh = self.tracked_forecast_kwh
        if forecast_kwh < MIN_FORECAST_KWH:
            return None
        return min(MAX_RATIO, max(MIN_RATIO, self.actual_kwh / forecast_kwh))

    def as_dict(self) -> dict[str, Any]:
        """Return the state to persist."""
        return {
            "day": self.day.isoformat() if self.day else None,
            "baseline_forecast_kwh": self.baseline_forecast_kwh,
            "latest_forecast_kwh": self.latest_forecast_kwh,
            "actual_kwh": self.actual_kwh,
            "baseline_energy_kwh": self.baseline_energy_kwh,
            "latest_energy_kwh": self.latest_energy_kwh,
        }

    def restore(self, data: dict[str, Any] | None, today: date, *, energy_counter: bool = False) -> None:
        """Restore state saved earlier today; anything older belongs to a previous day."""
        if not data or data.get("day") != today.isoformat():
            return
        try:
            baseline = data.get("baseline_forecast_kwh")
            self.baseline_forecast_kwh = None if baseline is None else float(baseline)
            self.latest_forecast_kwh = float(data.get("latest_forecast_kwh", 0.0))
            self.actual_kwh = max(0.0, float(data.get("actual_kwh", 0.0)))
            energy = data.get("baseline_energy_kwh")
            self.baseline_energy_kwh = None if energy is None else float(energy)
            self.latest_energy_kwh = float(data.get("latest_energy_kwh", 0.0))
        except TypeError, ValueError:
            self._clear()
            return
        counter_mismatch = (self.baseline_energy_kwh is not None) != energy_counter
        behind = self.baseline_forecast_kwh is not None and self.latest_forecast_kwh < self.baseline_forecast_kwh
        if counter_mismatch or behind:
            self._clear()
            return
        self.day = today

    def _clear(self) -> None:
        """Forget the measurement."""
        self.baseline_forecast_kwh = None
        self.latest_forecast_kwh = 0.0
        self.actual_kwh = 0.0
        self.baseline_energy_kwh = None
        self.latest_energy_kwh = 0.0
