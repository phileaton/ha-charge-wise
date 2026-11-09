"""Confirm sustained current shortfalls without changing charger control."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import TYPE_CHECKING

_CONFIRMATION = timedelta(minutes=5)
_RECOVERY = timedelta(minutes=1)


@dataclass
class EvUnderDrawingDetector:
    """Track sustained under-drawing and recovery within a charging session."""

    active: bool = False
    next_update_at: datetime | None = None
    _since: datetime | None = None

    def update(
        self,
        now: datetime,
        *,
        charging: bool,
        offered_a: float | None,
        measured_a: float | None,
    ) -> bool | None:
        """Return unknown for missing measurements and clear immediately outside charging."""
        valid = (
            offered_a is not None
            and measured_a is not None
            and isfinite(offered_a)
            and isfinite(measured_a)
            and offered_a > 0
            and measured_a >= 0
        )
        if not charging or not valid:
            self.active = False
            self._since = self.next_update_at = None
            return False if valid else None

        if TYPE_CHECKING:
            assert offered_a is not None and measured_a is not None
        shortfall = offered_a - measured_a
        under_drawing = shortfall >= 2 and shortfall >= offered_a * 0.2
        if under_drawing == self.active:
            self._since = self.next_update_at = None
            return self.active

        if self._since is None:
            self._since = now
        self.next_update_at = self._since + (_RECOVERY if self.active else _CONFIRMATION)
        if now >= self.next_update_at:
            self.active = under_drawing
            self._since = self.next_update_at = None
        return self.active
