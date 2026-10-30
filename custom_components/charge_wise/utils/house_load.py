"""Learned house consumption, kept as time-weighted moving averages per hour of day."""

from datetime import datetime, timedelta
from math import exp, isfinite
from typing import Any

_SECONDS_PER_HOUR = 3600
_HOURS_PER_DAY = 24


class HouseLoadProfile:
    """Average house power overall and for each local hour, adapting over a number of days."""

    def __init__(self, window_days: float) -> None:
        """Start empty; the first reading seeds the averages."""
        self._window_s = max(window_days, 0.1) * _SECONDS_PER_HOUR * _HOURS_PER_DAY
        self.overall_w: float | None = None
        self.hourly_w: list[float | None] = [None] * _HOURS_PER_DAY
        self._last_power_w: float | None = None
        self._last_time: datetime | None = None

    def observe(self, power_w: float | None, now: datetime) -> None:
        """Credit the previous reading for the time it was held, then remember the new one."""
        if self._last_power_w is not None and self._last_time is not None and now > self._last_time:
            self._integrate(self._last_power_w, self._last_time, now)
        if power_w is None or not isfinite(power_w):
            self._last_power_w = None
            self._last_time = None
            return
        value = max(0.0, power_w)
        if self.overall_w is None:
            self.overall_w = value
        self._last_power_w = value
        self._last_time = now

    def _integrate(self, power_w: float, start: datetime, end: datetime) -> None:
        cursor = start
        while cursor < end:
            hour_end = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_end = min(hour_end, end)
            seconds = (segment_end - cursor).total_seconds()
            hour = cursor.hour
            self.overall_w = self._blend(self.overall_w, power_w, seconds, self._window_s)
            # An hour only gets one hour of samples per day, so its time constant is one hour per day of window.
            self.hourly_w[hour] = self._blend(
                self.hourly_w[hour],
                power_w,
                seconds,
                self._window_s / _HOURS_PER_DAY,
            )
            cursor = segment_end

    @staticmethod
    def _blend(average: float | None, sample: float, seconds: float, time_constant_s: float) -> float:
        if average is None:
            return sample
        weight = 1 - exp(-seconds / time_constant_s)
        return average + (sample - average) * weight

    def expected_energy_kwh(self, start: datetime, end: datetime, fallback_w: float) -> float:
        """Return the expected consumption between two local times, using the overall average for unseen hours."""
        total_wh = 0.0
        cursor = start
        while cursor < end:
            hour_end = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_end = min(hour_end, end)
            power_w = self.hourly_w[cursor.hour]
            if power_w is None:
                power_w = self.overall_w if self.overall_w is not None else fallback_w
            total_wh += power_w * (segment_end - cursor).total_seconds() / _SECONDS_PER_HOUR
            cursor = segment_end
        return total_wh / 1000

    def as_dict(self) -> dict[str, Any]:
        """Return the learned averages for storage."""
        return {"overall_w": self.overall_w, "hourly_w": list(self.hourly_w)}

    def restore(self, data: Any) -> None:
        """Load stored averages, ignoring anything malformed."""
        if not isinstance(data, dict):
            return
        overall = data.get("overall_w")
        hourly = data.get("hourly_w")
        if isinstance(overall, int | float) and _is_number(overall):
            self.overall_w = float(overall)
        if isinstance(hourly, list) and len(hourly) == _HOURS_PER_DAY:
            self.hourly_w = [
                float(value) if isinstance(value, int | float) and _is_number(value) else None for value in hourly
            ]


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value)
