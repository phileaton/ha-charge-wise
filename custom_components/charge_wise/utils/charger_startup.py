"""Bound charger command confirmation and detect a session that never draws power."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isclose

from custom_components.charge_wise.utils.charger_status import ChargerSessionStatus

COMMAND_CONFIRMATION = timedelta(seconds=30)
CHARGING_CONFIRMATION = timedelta(minutes=5)


@dataclass
class ChargeWiseStartupMonitor:
    """Latch unsafe command failures and report missing charging power separately."""

    failed: bool = False
    not_drawing: bool = False
    current_deadline: datetime | None = None
    switch_deadline: datetime | None = None
    charging_deadline: datetime | None = None

    def reset(self) -> None:
        """Clear the failure and all pending confirmations."""
        self.failed = False
        self.not_drawing = False
        self._clear_deadlines()

    def fail(self) -> None:
        """Latch a command failure and cancel pending checks."""
        self.failed = True
        self._clear_deadlines()

    def current_requested(self, now: datetime) -> None:
        """Begin the current response window when its limit command is sent."""
        self.current_deadline = self.current_deadline or now + COMMAND_CONFIRMATION

    def start_requested(self, now: datetime) -> None:
        """Begin the switch response window when its start command is sent."""
        self.switch_deadline = self.switch_deadline or now + COMMAND_CONFIRMATION

    def confirm_commands(self, *, target_a: float, observed_a: float | None, switch_on: bool) -> None:
        """Clear deadlines immediately when a service call publishes its acknowledgement."""
        if observed_a is not None and isclose(observed_a, target_a, abs_tol=0.01):
            self.current_deadline = None
        if switch_on:
            self.switch_deadline = None

    def _clear_deadlines(self) -> None:
        self.current_deadline = self.switch_deadline = self.charging_deadline = None

    @property
    def next_update_at(self) -> datetime | None:
        """Return the first confirmation deadline that still needs evaluation."""
        deadlines = [value for value in (self.current_deadline, self.switch_deadline, self.charging_deadline) if value]
        return min(deadlines) if deadlines else None

    def update(
        self,
        now: datetime,
        *,
        requested: bool,
        native_solar: bool,
        target_a: float,
        observed_a: float | None,
        switch_on: bool,
        charging: bool | None,
        session: ChargerSessionStatus | None,
    ) -> bool:
        """Require command confirmation in 30 seconds and report no power after five minutes.

        Explicitly paused or finished sessions and charger-managed solar need no power deadline.
        Changing the requested current does not extend a pending confirmation deadline.
        """
        if self.failed:
            return True
        if not requested or native_solar:
            self.not_drawing = False
            self._clear_deadlines()
            return False
        current_confirmed = observed_a is not None and isclose(observed_a, target_a, abs_tol=0.01)
        if current_confirmed:
            self.current_deadline = None
        elif observed_a is None:
            self.current_deadline = self.current_deadline or now + COMMAND_CONFIRMATION
        if switch_on:
            self.switch_deadline = None
        no_power_expected = session in (ChargerSessionStatus.PAUSED, ChargerSessionStatus.FINISHED)
        if not switch_on or charging is True or no_power_expected:
            self.not_drawing = False
            self.charging_deadline = None
        elif not self.not_drawing:
            self.charging_deadline = self.charging_deadline or now + CHARGING_CONFIRMATION
            if now >= self.charging_deadline:
                self.not_drawing = True
                self.charging_deadline = None
        command_deadlines = [deadline for deadline in (self.current_deadline, self.switch_deadline) if deadline]
        if command_deadlines and now >= min(command_deadlines):
            self.fail()
        return self.failed
