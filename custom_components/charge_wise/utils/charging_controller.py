"""Pure charging decision logic for Charge Wise."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from math import ceil, floor


class ControllerStatus(StrEnum):
    """Stable high-level controller status values."""

    OFF = "off"
    WAITING = "waiting"
    CHARGING = "charging"
    PAUSED = "paused"
    ERROR = "error"


class ChargeWiseReason(StrEnum):
    """Reason for the current controller decision."""

    OFF = "off"
    NO_SOURCE = "no_source"
    MANUAL = "manual"
    OFFPEAK_WINDOW = "offpeak_window"
    OFFPEAK_WAITING = "offpeak_waiting"
    SOLAR_WAITING = "solar_waiting"
    COOLDOWN = "cooldown"
    GRID_UNAVAILABLE = "grid_unavailable"
    CHARGER_POWER_UNAVAILABLE = "charger_power_unavailable"
    BATTERY_UNAVAILABLE = "battery_unavailable"
    EV_STATUS_UNAVAILABLE = "ev_status_unavailable"
    EV_DISCONNECTED = "ev_disconnected"
    BATTERY_CONFIRMING = "battery_confirming"
    BATTERY_PROTECTION = "battery_protection"
    BATTERY_RECOVERY = "battery_recovery"
    LOW_SOLAR_CONFIRMING = "low_solar_confirming"
    LOW_SOLAR = "low_solar"
    SOLAR_CHARGING = "solar_charging"
    EV_FIRST = "ev_first"
    HARDWARE_LIMIT = "hardware_limit"
    CONTROL_FAILED = "control_failed"


@dataclass(frozen=True)
class ControllerConfig:
    """User-configurable limits and Solar control thresholds."""

    minimum_current_a: int = 6
    maximum_current_a: int = 32
    voltage_v: int = 240
    solar_start_w: int = 1800
    low_solar_confirmation_s: int = 90
    cooldown_s: int = 180
    battery_discharge_w: int = 300
    battery_recovery_w: int = 150
    battery_confirmation_s: int = 90
    battery_recovery_confirmation_s: int = 90
    current_deadband_a: float = 1.0


@dataclass(frozen=True)
class ControlSettings:
    """User-controlled charging sources and the current off-peak window state."""

    enabled: bool = False
    solar_enabled: bool = False
    offpeak_enabled: bool = False
    manual_override: bool = False
    manual_current_a: float = 6
    offpeak_current_a: float = 6
    offpeak_active: bool = False
    offpeak_next_change: datetime | None = None


@dataclass(frozen=True)
class ControllerInput:
    """Normalized Home Assistant readings used by the controller."""

    grid_power_w: float | None
    charger_power_w: float | None
    battery_discharge_w: float | None
    battery_configured: bool
    ev_connected: bool | None
    ev_connected_configured: bool
    charger_enabled: bool
    current_target_a: float | None
    hardware_maximum_a: float | None
    ev_first_boost_w: float = 0.0


@dataclass(frozen=True)
class ControllerDecision:
    """Desired charger state and the next required evaluation time."""

    status: ControllerStatus
    reason: ChargeWiseReason
    available_solar_w: float | None
    requested_current_a: float
    charger_enabled: bool
    battery_protection_active: bool | None
    next_update_at: datetime | None = None


class ChargeWiseController:
    """Calculate safe charger commands from a snapshot of Home Assistant state."""

    def __init__(self, config: ControllerConfig) -> None:
        """Initialize controller timers and latches."""
        self.config = config
        self._solar_running = False
        self._low_solar_since: datetime | None = None
        self._battery_discharge_since: datetime | None = None
        self._battery_recovery_since: datetime | None = None
        self._cooldown_until: datetime | None = None
        self._battery_protection_active = False
        self._battery_current_reduction_a = 0
        self._safety_paused = False

    def start_cooldown(self, now: datetime) -> None:
        """Delay a Solar start after a restart so restored switches never cause an immediate start."""
        self._cooldown_until = now + timedelta(seconds=self.config.cooldown_s)

    def _reset_solar(self) -> None:
        """Drop Solar timers and latches when Solar stops owning the charger."""
        self._solar_running = False
        self._low_solar_since = None
        self._battery_discharge_since = None
        self._battery_recovery_since = None
        self._battery_protection_active = False
        self._battery_current_reduction_a = 0
        self._safety_paused = False
        self._cooldown_until = None

    def evaluate(
        self,
        settings: ControlSettings,
        readings: ControllerInput,
        now: datetime,
    ) -> ControllerDecision:
        """Return the desired charging state without performing I/O."""
        if not settings.enabled:
            self._reset_solar()
            return self._decision(ControllerStatus.OFF, ChargeWiseReason.OFF, readings, 0, False)

        if readings.ev_connected_configured:
            if readings.ev_connected is None:
                return self._pause(ChargeWiseReason.EV_STATUS_UNAVAILABLE, readings, now)
            if not readings.ev_connected:
                return self._pause(ChargeWiseReason.EV_DISCONNECTED, readings, now)
        self._safety_paused = False

        if settings.manual_override:
            self._reset_solar()
            return self._fixed_current_decision(settings.manual_current_a, ChargeWiseReason.MANUAL, readings)

        solar = self._evaluate_solar_source(settings, readings, now)
        offpeak = self._evaluate_offpeak(settings, readings)

        if offpeak is not None and offpeak.charger_enabled:
            if solar is not None and solar.charger_enabled and solar.requested_current_a >= offpeak.requested_current_a:
                chosen = solar
            else:
                chosen = replace(
                    offpeak,
                    available_solar_w=solar.available_solar_w if solar else None,
                    battery_protection_active=solar.battery_protection_active if solar else None,
                )
        elif solar is not None:
            chosen = solar
        elif offpeak is not None:
            chosen = offpeak
        elif settings.offpeak_enabled:
            chosen = self._decision(ControllerStatus.WAITING, ChargeWiseReason.OFFPEAK_WAITING, readings, 0, False)
        else:
            chosen = self._decision(ControllerStatus.OFF, ChargeWiseReason.NO_SOURCE, readings, 0, False)

        deadlines = [chosen.next_update_at, solar.next_update_at if solar else None]
        if settings.offpeak_enabled:
            deadlines.append(settings.offpeak_next_change)
        return replace(chosen, next_update_at=self._future_deadline([d for d in deadlines if d], now))

    def _evaluate_solar_source(
        self,
        settings: ControlSettings,
        readings: ControllerInput,
        now: datetime,
    ) -> ControllerDecision | None:
        """Run the Solar state machine only while the Solar switch is on."""
        if not settings.solar_enabled:
            self._reset_solar()
            return None
        if not self._solar_running:
            self._solar_running = True
        decision = self._evaluate_solar(readings, now)
        if readings.ev_first_boost_w > 0 and decision.reason is ChargeWiseReason.SOLAR_CHARGING:
            return replace(decision, reason=ChargeWiseReason.EV_FIRST)
        return decision

    def _evaluate_offpeak(
        self,
        settings: ControlSettings,
        readings: ControllerInput,
    ) -> ControllerDecision | None:
        """Charge from the grid at the off-peak current while a window is active."""
        if not settings.offpeak_enabled or not settings.offpeak_active:
            return None
        decision = self._fixed_current_decision(settings.offpeak_current_a, ChargeWiseReason.OFFPEAK_WINDOW, readings)
        return replace(decision, next_update_at=settings.offpeak_next_change)

    def _fixed_current_decision(
        self,
        current_a: float,
        reason: ChargeWiseReason,
        readings: ControllerInput,
    ) -> ControllerDecision:
        """Apply a fixed target within configured and hardware limits."""
        maximum = self._effective_maximum(readings)
        if maximum < self.config.minimum_current_a:
            return self._decision(
                ControllerStatus.PAUSED,
                ChargeWiseReason.HARDWARE_LIMIT,
                readings,
                0,
                False,
            )
        target = min(max(current_a, self.config.minimum_current_a), maximum)
        return self._decision(ControllerStatus.CHARGING, reason, readings, target, True)

    def _evaluate_solar(self, readings: ControllerInput, now: datetime) -> ControllerDecision:
        """Calculate a Solar target after validating all configured safety inputs."""
        if readings.grid_power_w is None:
            return self._pause(ChargeWiseReason.GRID_UNAVAILABLE, readings, now)
        if readings.charger_power_w is None:
            return self._pause(ChargeWiseReason.CHARGER_POWER_UNAVAILABLE, readings, now)
        if readings.battery_configured and readings.battery_discharge_w is None:
            return self._pause(ChargeWiseReason.BATTERY_UNAVAILABLE, readings, now)

        available_solar_w = max(0.0, readings.charger_power_w - readings.grid_power_w + readings.ev_first_boost_w)
        next_updates = self._update_battery_protection(readings, now)
        low_solar_decision = self._evaluate_low_solar(readings, available_solar_w, now, next_updates)
        if low_solar_decision is not None:
            return low_solar_decision

        maximum = self._effective_maximum(readings)
        if maximum < self.config.minimum_current_a:
            return self._solar_decision(
                ControllerStatus.PAUSED,
                ChargeWiseReason.HARDWARE_LIMIT,
                readings,
                0,
                False,
                available_solar_w,
                next_updates,
                now,
            )

        if not readings.charger_enabled and available_solar_w < self.config.solar_start_w:
            return self._solar_decision(
                ControllerStatus.WAITING,
                ChargeWiseReason.SOLAR_WAITING,
                readings,
                0,
                False,
                available_solar_w,
                next_updates,
                now,
            )

        if not readings.charger_enabled and self._cooldown_until is not None and now < self._cooldown_until:
            next_updates.append(self._cooldown_until)
            return self._solar_decision(
                ControllerStatus.WAITING,
                ChargeWiseReason.COOLDOWN,
                readings,
                0,
                False,
                available_solar_w,
                next_updates,
                now,
            )

        return self._solar_charging_decision(readings, available_solar_w, maximum, next_updates, now)

    def _update_battery_protection(self, readings: ControllerInput, now: datetime) -> list[datetime]:
        """Advance battery confirmation/recovery timers and return their deadlines."""
        if not readings.battery_configured:
            return []

        deadlines: list[datetime] = []
        battery_discharge_w = max(0.0, readings.battery_discharge_w or 0.0)
        if battery_discharge_w > self.config.battery_discharge_w:
            self._battery_recovery_since = None
            if self._battery_discharge_since is None:
                self._battery_discharge_since = now
            battery_deadline = self._battery_discharge_since + timedelta(
                seconds=self.config.battery_confirmation_s,
            )
            if now < battery_deadline:
                deadlines.append(battery_deadline)
            elif not self._battery_protection_active:
                self._battery_protection_active = True
                self._battery_current_reduction_a = ceil(battery_discharge_w / self.config.voltage_v)
                self._cooldown_until = now + timedelta(seconds=self.config.cooldown_s)
                deadlines.append(self._cooldown_until)
        else:
            self._battery_discharge_since = None

        if not self._battery_protection_active:
            return deadlines

        if battery_discharge_w >= self.config.battery_recovery_w:
            self._battery_recovery_since = None
            self._battery_current_reduction_a = ceil(battery_discharge_w / self.config.voltage_v)
            return deadlines

        if self._battery_recovery_since is None:
            self._battery_recovery_since = now
        recovery_deadline = self._battery_recovery_since + timedelta(
            seconds=self.config.battery_recovery_confirmation_s,
        )
        if now >= recovery_deadline and (self._cooldown_until is None or now >= self._cooldown_until):
            self._battery_protection_active = False
            self._battery_current_reduction_a = 0
            self._battery_recovery_since = None
            self._cooldown_until = None
        else:
            deadlines.extend(
                deadline
                for deadline in (recovery_deadline, self._cooldown_until)
                if deadline is not None and deadline > now
            )
        return deadlines

    def _evaluate_low_solar(
        self,
        readings: ControllerInput,
        available_solar_w: float,
        now: datetime,
        next_updates: list[datetime],
    ) -> ControllerDecision | None:
        """Hold minimum current briefly, then stop after confirmed low solar power."""
        minimum_power_w = self.config.minimum_current_a * self.config.voltage_v
        if available_solar_w >= minimum_power_w:
            self._low_solar_since = None
            return None
        if not readings.charger_enabled:
            return None

        if self._low_solar_since is None:
            self._low_solar_since = now
        low_solar_deadline = self._low_solar_since + timedelta(
            seconds=self.config.low_solar_confirmation_s,
        )
        if now < low_solar_deadline:
            next_updates.append(low_solar_deadline)
            return self._solar_decision(
                ControllerStatus.CHARGING,
                ChargeWiseReason.LOW_SOLAR_CONFIRMING,
                readings,
                self.config.minimum_current_a,
                True,
                available_solar_w,
                next_updates,
                now,
            )

        if self._cooldown_until is None or now >= self._cooldown_until:
            self._cooldown_until = now + timedelta(seconds=self.config.cooldown_s)
        next_updates.append(self._cooldown_until)
        return self._solar_decision(
            ControllerStatus.PAUSED,
            ChargeWiseReason.LOW_SOLAR,
            readings,
            0,
            False,
            available_solar_w,
            next_updates,
            now,
        )

    def _solar_charging_decision(
        self,
        readings: ControllerInput,
        available_solar_w: float,
        maximum: float,
        next_updates: list[datetime],
        now: datetime,
    ) -> ControllerDecision:
        """Build a bounded solar target and apply the current deadband."""
        target = min(
            max(floor(available_solar_w / self.config.voltage_v), self.config.minimum_current_a),
            maximum,
        )
        if self._battery_protection_active:
            target -= self._battery_current_reduction_a
            if target < self.config.minimum_current_a:
                return self._solar_decision(
                    ControllerStatus.PAUSED,
                    ChargeWiseReason.BATTERY_PROTECTION,
                    readings,
                    0,
                    False,
                    available_solar_w,
                    next_updates,
                    now,
                )

        if (
            readings.charger_enabled
            and readings.current_target_a is not None
            and abs(target - readings.current_target_a) < self.config.current_deadband_a
        ):
            target = min(max(readings.current_target_a, self.config.minimum_current_a), maximum)

        reason = self._charging_reason(next_updates, now)
        return self._solar_decision(
            ControllerStatus.CHARGING,
            reason,
            readings,
            target,
            True,
            available_solar_w,
            next_updates,
            now,
        )

    def _charging_reason(self, next_updates: list[datetime], now: datetime) -> ChargeWiseReason:
        """Choose the most relevant reason for an active Solar decision."""
        if self._battery_protection_active:
            if self._battery_recovery_since is not None:
                return ChargeWiseReason.BATTERY_RECOVERY
            return ChargeWiseReason.BATTERY_PROTECTION
        if self._battery_discharge_since is not None:
            battery_deadline = self._battery_discharge_since + timedelta(
                seconds=self.config.battery_confirmation_s,
            )
            if battery_deadline > now:
                next_updates.append(battery_deadline)
                return ChargeWiseReason.BATTERY_CONFIRMING
        return ChargeWiseReason.SOLAR_CHARGING

    def _solar_decision(
        self,
        status: ControllerStatus,
        reason: ChargeWiseReason,
        readings: ControllerInput,
        current_a: float,
        enabled: bool,
        available_solar_w: float,
        deadlines: list[datetime],
        now: datetime,
    ) -> ControllerDecision:
        """Build a Solar decision with the earliest pending timer."""
        return self._decision(
            status,
            reason,
            readings,
            current_a,
            enabled,
            available_solar_w=available_solar_w,
            next_update_at=self._future_deadline(deadlines, now),
        )

    def _pause(
        self,
        reason: ChargeWiseReason,
        readings: ControllerInput,
        now: datetime,
    ) -> ControllerDecision:
        """Stop charging while a safety input is missing or unsafe."""
        if not self._safety_paused:
            self._cooldown_until = now + timedelta(seconds=self.config.cooldown_s)
        self._safety_paused = True
        self._low_solar_since = None
        self._battery_discharge_since = None
        self._battery_recovery_since = None
        return self._decision(
            ControllerStatus.PAUSED,
            reason,
            readings,
            0,
            False,
            next_update_at=self._cooldown_until,
        )

    def _decision(
        self,
        status: ControllerStatus,
        reason: ChargeWiseReason,
        readings: ControllerInput,
        current_a: float,
        enabled: bool,
        *,
        available_solar_w: float | None = None,
        next_update_at: datetime | None = None,
    ) -> ControllerDecision:
        """Build a consistent decision snapshot."""
        protection = self._battery_protection_active if readings.battery_configured else None
        return ControllerDecision(
            status=status,
            reason=reason,
            available_solar_w=available_solar_w,
            requested_current_a=current_a,
            charger_enabled=enabled,
            battery_protection_active=protection,
            next_update_at=next_update_at,
        )

    def _effective_maximum(self, readings: ControllerInput) -> float:
        """Apply the optional hardware ceiling below the configured maximum."""
        maximum = float(self.config.maximum_current_a)
        if readings.hardware_maximum_a is not None:
            maximum = min(maximum, readings.hardware_maximum_a)
        return maximum

    @staticmethod
    def _future_deadline(deadlines: list[datetime], now: datetime) -> datetime | None:
        """Return the earliest pending timer deadline."""
        future = [deadline for deadline in deadlines if deadline > now]
        return min(future) if future else None
