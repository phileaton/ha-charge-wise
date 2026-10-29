"""Unit tests for Charge Wise charging decisions."""

from datetime import UTC, datetime, timedelta

from custom_components.charge_wise.utils.charging_controller import (
    ChargeWiseController,
    ChargeWiseMode,
    ChargeWiseReason,
    ControllerConfig,
    ControllerInput,
    ControllerStatus,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _readings(
    *,
    grid_power_w: float | None = -2000,
    charger_power_w: float | None = 0,
    battery_discharge_w: float | None = 0,
    battery_configured: bool = True,
    ev_connected: bool | None = True,
    ev_connected_configured: bool = True,
    charger_enabled: bool = False,
    current_target_a: float | None = 6,
    hardware_maximum_a: float | None = 32,
) -> ControllerInput:
    """Build a normal controller input with selected safety sensors."""
    return ControllerInput(
        grid_power_w=grid_power_w,
        charger_power_w=charger_power_w,
        battery_discharge_w=battery_discharge_w,
        battery_configured=battery_configured,
        ev_connected=ev_connected,
        ev_connected_configured=ev_connected_configured,
        charger_enabled=charger_enabled,
        current_target_a=current_target_a,
        hardware_maximum_a=hardware_maximum_a,
    )


def test_off_mode_never_requests_charging() -> None:
    """Off mode returns a disabled decision."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        ChargeWiseMode.OFF,
        10,
        _readings(),
        START,
    )

    assert decision.status is ControllerStatus.OFF
    assert decision.reason is ChargeWiseReason.OFF
    assert not decision.charger_enabled
    assert decision.requested_current_a == 0


def test_solar_mode_starts_only_after_the_start_threshold() -> None:
    """Solar mode waits below its start threshold and floors current to available power."""
    controller = ChargeWiseController(ControllerConfig())
    waiting = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        _readings(grid_power_w=-1799),
        START,
    )
    charging = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        _readings(grid_power_w=-1800),
        START,
    )

    assert waiting.status is ControllerStatus.WAITING
    assert not waiting.charger_enabled
    assert charging.status is ControllerStatus.CHARGING
    assert charging.requested_current_a == 7


def test_battery_protection_is_confirmed_and_reduces_full_discharge() -> None:
    """Battery protection waits 90 seconds and then subtracts the full discharge current."""
    controller = ChargeWiseController(ControllerConfig())
    readings = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=600,
        charger_enabled=True,
        current_target_a=12,
    )
    confirming = controller.evaluate(ChargeWiseMode.SOLAR, 6, readings, START)
    protected = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        readings,
        START + timedelta(seconds=90),
    )

    assert confirming.reason is ChargeWiseReason.BATTERY_CONFIRMING
    assert confirming.requested_current_a == 12
    assert protected.reason is ChargeWiseReason.BATTERY_PROTECTION
    assert protected.requested_current_a == 9
    assert protected.battery_protection_active


def test_battery_protection_stops_below_the_minimum_current() -> None:
    """Protection stops charging instead of requesting less than the configured minimum."""
    controller = ChargeWiseController(ControllerConfig())
    readings = _readings(
        grid_power_w=0,
        charger_power_w=2000,
        battery_discharge_w=720,
        charger_enabled=True,
        current_target_a=8,
    )
    controller.evaluate(ChargeWiseMode.SOLAR, 6, readings, START)

    decision = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        readings,
        START + timedelta(seconds=90),
    )

    assert decision.status is ControllerStatus.PAUSED
    assert decision.reason is ChargeWiseReason.BATTERY_PROTECTION
    assert not decision.charger_enabled


def test_battery_recovery_waits_for_confirmation_and_cooldown() -> None:
    """The battery correction remains until both recovery conditions have elapsed."""
    controller = ChargeWiseController(ControllerConfig())
    high = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=600,
        charger_enabled=True,
        current_target_a=12,
    )
    controller.evaluate(ChargeWiseMode.SOLAR, 6, high, START)
    controller.evaluate(ChargeWiseMode.SOLAR, 6, high, START + timedelta(seconds=90))
    low = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=0,
        charger_enabled=True,
        current_target_a=9,
    )

    recovering = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        low,
        START + timedelta(seconds=181),
    )
    recovered = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        low,
        START + timedelta(seconds=271),
    )

    assert recovering.reason is ChargeWiseReason.BATTERY_RECOVERY
    assert recovering.requested_current_a == 9
    assert recovering.battery_protection_active
    assert recovered.reason is ChargeWiseReason.SOLAR_CHARGING
    assert recovered.requested_current_a == 12
    assert not recovered.battery_protection_active


def test_invalid_configured_battery_reading_pauses_solar() -> None:
    """A missing configured battery reading cannot silently disable protection."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        ChargeWiseMode.SOLAR,
        6,
        _readings(battery_discharge_w=None),
        START,
    )

    assert decision.status is ControllerStatus.PAUSED
    assert decision.reason is ChargeWiseReason.BATTERY_UNAVAILABLE
    assert not decision.charger_enabled


def test_low_solar_confirmation_stops_charging_after_ninety_seconds() -> None:
    """Low solar power is confirmed before charging is stopped."""
    controller = ChargeWiseController(ControllerConfig())
    readings = _readings(
        grid_power_w=0,
        charger_power_w=1000,
        charger_enabled=True,
        current_target_a=6,
    )
    confirming = controller.evaluate(ChargeWiseMode.SOLAR, 6, readings, START)
    stopped = controller.evaluate(
        ChargeWiseMode.SOLAR,
        6,
        readings,
        START + timedelta(seconds=90),
    )

    assert confirming.reason is ChargeWiseReason.LOW_SOLAR_CONFIRMING
    assert confirming.charger_enabled
    assert stopped.status is ControllerStatus.PAUSED
    assert stopped.reason is ChargeWiseReason.LOW_SOLAR
    assert not stopped.charger_enabled


def test_manual_mode_respects_hardware_ceiling() -> None:
    """Manual current is clamped by the configured and live hardware maxima."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        ChargeWiseMode.MANUAL,
        20,
        _readings(
            hardware_maximum_a=16,
            grid_power_w=None,
            charger_power_w=None,
        ),
        START,
    )

    assert decision.status is ControllerStatus.CHARGING
    assert decision.requested_current_a == 16
    assert decision.charger_enabled
