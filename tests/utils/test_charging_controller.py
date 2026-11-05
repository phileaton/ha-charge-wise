"""Unit tests for Charge Wise charging decisions."""

from datetime import UTC, datetime, timedelta

from custom_components.charge_wise.utils.charging_controller import (
    ChargeWiseController,
    ChargeWiseReason,
    ControllerConfig,
    ControllerInput,
    ControllerStatus,
    ControlSettings,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
OFF = ControlSettings()
SOLAR = ControlSettings(enabled=True, solar_enabled=True)
MANUAL = ControlSettings(enabled=True, manual_override=True, manual_current_a=20)


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
    ev_first_boost_w: float = 0.0,
    ev_first_blocked: bool = False,
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
        ev_first_boost_w=ev_first_boost_w,
        ev_first_blocked=ev_first_blocked,
    )


def test_master_off_never_requests_charging() -> None:
    """Master off returns a disabled decision."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        OFF,
        _readings(),
        START,
    )

    assert decision.status is ControllerStatus.OFF
    assert decision.reason is ChargeWiseReason.OFF
    assert not decision.charger_enabled
    assert decision.requested_current_a == 0


def test_solar_mode_starts_only_after_the_start_threshold() -> None:
    """Solar mode waits below its start threshold and floors current to available power."""
    controller = ChargeWiseController(ControllerConfig(solar_start_confirmation_s=0))
    waiting = controller.evaluate(
        SOLAR,
        _readings(grid_power_w=-1799),
        START,
    )
    charging = controller.evaluate(
        SOLAR,
        _readings(grid_power_w=-1800),
        START,
    )

    assert waiting.status is ControllerStatus.WAITING
    assert not waiting.charger_enabled
    assert charging.status is ControllerStatus.CHARGING
    assert charging.requested_current_a == 7


def test_solar_start_must_hold_before_the_charger_is_started() -> None:
    """A brief surplus spike never starts the charger; a sustained one does."""
    controller = ChargeWiseController(ControllerConfig(solar_start_confirmation_s=60))
    spike = controller.evaluate(SOLAR, _readings(grid_power_w=-3000), START)
    gone = controller.evaluate(SOLAR, _readings(grid_power_w=-100), START + timedelta(seconds=1))
    again = controller.evaluate(SOLAR, _readings(grid_power_w=-3000), START + timedelta(seconds=2))
    early = controller.evaluate(SOLAR, _readings(grid_power_w=-3000), START + timedelta(seconds=61))
    held = controller.evaluate(SOLAR, _readings(grid_power_w=-3000), START + timedelta(seconds=62))

    assert not spike.charger_enabled
    assert spike.reason is ChargeWiseReason.SOLAR_WAITING
    assert spike.next_update_at == START + timedelta(seconds=60)
    assert not gone.charger_enabled
    assert not again.charger_enabled
    assert not early.charger_enabled
    assert held.charger_enabled
    assert held.status is ControllerStatus.CHARGING


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
    confirming = controller.evaluate(SOLAR, readings, START)
    protected = controller.evaluate(
        SOLAR,
        readings,
        START + timedelta(seconds=90),
    )

    assert confirming.reason is ChargeWiseReason.BATTERY_CONFIRMING
    assert confirming.requested_current_a == 12
    assert protected.reason is ChargeWiseReason.BATTERY_PROTECTION
    assert protected.requested_current_a == 9
    assert protected.battery_protection_active


def test_battery_protection_ignores_a_brief_discharge_spike() -> None:
    """A short spike while the charger ramps down does not enlarge the cut or pause charging."""
    controller = ChargeWiseController(ControllerConfig())
    steady = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=600,
        charger_enabled=True,
        current_target_a=12,
    )
    spike = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=3000,
        charger_enabled=True,
        current_target_a=12,
    )
    controller.evaluate(SOLAR, steady, START)
    controller.evaluate(SOLAR, steady, START + timedelta(seconds=90))

    during_spike = controller.evaluate(SOLAR, spike, START + timedelta(seconds=100))
    after_spike = controller.evaluate(SOLAR, steady, START + timedelta(seconds=105))
    sustained = controller.evaluate(SOLAR, spike, START + timedelta(seconds=110))
    confirmed = controller.evaluate(SOLAR, spike, START + timedelta(seconds=200))

    assert during_spike.requested_current_a == 9
    assert after_spike.requested_current_a == 9
    assert sustained.requested_current_a == 9
    assert confirmed.status is ControllerStatus.PAUSED


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
    controller.evaluate(SOLAR, readings, START)

    decision = controller.evaluate(
        SOLAR,
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
    controller.evaluate(SOLAR, high, START)
    controller.evaluate(SOLAR, high, START + timedelta(seconds=90))
    low = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=0,
        charger_enabled=True,
        current_target_a=9,
    )

    recovering = controller.evaluate(
        SOLAR,
        low,
        START + timedelta(seconds=181),
    )
    recovered = controller.evaluate(
        SOLAR,
        low,
        START + timedelta(seconds=271),
    )

    assert recovering.reason is ChargeWiseReason.BATTERY_RECOVERY
    assert recovering.requested_current_a == 9
    assert recovering.battery_protection_active
    assert recovered.reason is ChargeWiseReason.SOLAR_CHARGING
    assert recovered.requested_current_a == 12
    assert not recovered.battery_protection_active


def test_battery_protection_recovers_when_recovery_threshold_is_zero() -> None:
    """Zero battery discharge starts recovery instead of keeping protection latched."""
    controller = ChargeWiseController(ControllerConfig(battery_recovery_w=0))
    high = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=600,
        charger_enabled=True,
        current_target_a=12,
    )
    controller.evaluate(SOLAR, high, START)
    controller.evaluate(SOLAR, high, START + timedelta(seconds=90))
    low = _readings(
        grid_power_w=0,
        charger_power_w=3000,
        battery_discharge_w=0,
        charger_enabled=True,
        current_target_a=9,
    )

    recovering = controller.evaluate(SOLAR, low, START + timedelta(seconds=181))
    recovered = controller.evaluate(SOLAR, low, START + timedelta(seconds=271))

    assert recovering.reason is ChargeWiseReason.BATTERY_RECOVERY
    assert recovering.battery_protection_active
    assert recovered.reason is ChargeWiseReason.SOLAR_CHARGING
    assert not recovered.battery_protection_active


def test_invalid_configured_battery_reading_pauses_solar() -> None:
    """A missing configured battery reading cannot silently disable protection."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        SOLAR,
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
    confirming = controller.evaluate(SOLAR, readings, START)
    stopped = controller.evaluate(
        SOLAR,
        readings,
        START + timedelta(seconds=90),
    )

    assert confirming.reason is ChargeWiseReason.LOW_SOLAR_CONFIRMING
    assert confirming.charger_enabled
    assert stopped.status is ControllerStatus.PAUSED
    assert stopped.reason is ChargeWiseReason.LOW_SOLAR
    assert not stopped.charger_enabled


def test_manual_override_respects_hardware_ceiling() -> None:
    """Manual current is clamped by the configured and live hardware maxima."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        MANUAL,
        _readings(
            hardware_maximum_a=16,
            grid_power_w=None,
            charger_power_w=None,
            ev_first_blocked=True,
        ),
        START,
    )

    assert decision.status is ControllerStatus.CHARGING
    assert decision.requested_current_a == 16
    assert decision.charger_enabled


def _offpeak(**overrides: object) -> ControlSettings:
    values: dict[str, object] = {
        "enabled": True,
        "offpeak_enabled": True,
        "offpeak_active": True,
        "offpeak_current_a": 10,
        "offpeak_next_change": START + timedelta(hours=2),
    }
    values.update(overrides)
    return ControlSettings(**values)  # type: ignore[arg-type]


def test_offpeak_window_charges_from_the_grid_without_solar() -> None:
    """An active window charges at the off-peak current even with no surplus."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        _offpeak(),
        _readings(grid_power_w=3000, charger_power_w=0, ev_first_blocked=True),
        START,
    )

    assert decision.status is ControllerStatus.CHARGING
    assert decision.reason is ChargeWiseReason.OFFPEAK_WINDOW
    assert decision.requested_current_a == 10
    assert decision.next_update_at == START + timedelta(hours=2)


def test_offpeak_outside_a_window_waits_and_schedules_the_next_boundary() -> None:
    """Outside a window nothing charges and the next boundary is the re-evaluation time."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        _offpeak(offpeak_active=False),
        _readings(),
        START,
    )

    assert decision.status is ControllerStatus.WAITING
    assert decision.reason is ChargeWiseReason.OFFPEAK_WAITING
    assert not decision.charger_enabled
    assert decision.next_update_at == START + timedelta(hours=2)


def test_highest_request_wins_when_solar_and_offpeak_are_on() -> None:
    """Solar above the off-peak current wins; below it, off-peak wins."""
    settings = _offpeak(solar_enabled=True, offpeak_current_a=10)
    high_solar = ChargeWiseController(ControllerConfig(solar_start_confirmation_s=0)).evaluate(
        settings,
        _readings(grid_power_w=-6000),
        START,
    )
    low_solar = ChargeWiseController(ControllerConfig(solar_start_confirmation_s=0)).evaluate(
        settings,
        _readings(grid_power_w=-2000),
        START,
    )

    assert high_solar.reason is ChargeWiseReason.SOLAR_CHARGING
    assert high_solar.requested_current_a == 25
    assert low_solar.reason is ChargeWiseReason.OFFPEAK_WINDOW
    assert low_solar.requested_current_a == 10
    assert low_solar.available_solar_w == 2000


def test_offpeak_ignores_missing_solar_sensors() -> None:
    """Grid charging does not depend on the Solar inputs."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        _offpeak(solar_enabled=True),
        _readings(grid_power_w=None, charger_power_w=None),
        START,
    )

    assert decision.reason is ChargeWiseReason.OFFPEAK_WINDOW
    assert decision.charger_enabled


def test_manual_override_beats_solar_and_offpeak() -> None:
    """Manual override uses its own current and ignores the other sources."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        _offpeak(solar_enabled=True, manual_override=True, manual_current_a=14),
        _readings(grid_power_w=-6000),
        START,
    )

    assert decision.reason is ChargeWiseReason.MANUAL
    assert decision.requested_current_a == 14


def test_offpeak_still_requires_a_connected_ev_and_respects_hardware_limit() -> None:
    """EV safety and the charger ceiling apply to off-peak charging."""
    controller = ChargeWiseController(ControllerConfig())
    disconnected = controller.evaluate(_offpeak(), _readings(ev_connected=False), START)
    limited = controller.evaluate(_offpeak(offpeak_current_a=30), _readings(hardware_maximum_a=16), START)

    assert disconnected.reason is ChargeWiseReason.EV_DISCONNECTED
    assert not disconnected.charger_enabled
    assert limited.requested_current_a == 16


def test_no_source_enabled_does_not_charge() -> None:
    """Master on with every source off requests nothing."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        ControlSettings(enabled=True),
        _readings(),
        START,
    )

    assert decision.status is ControllerStatus.OFF
    assert decision.reason is ChargeWiseReason.NO_SOURCE


def test_ev_first_boost_adds_battery_charge_power_to_the_solar_budget() -> None:
    """With the boost the EV may use power that would otherwise charge the battery."""
    controller = ChargeWiseController(ControllerConfig(solar_start_confirmation_s=0))
    plain = controller.evaluate(SOLAR, _readings(grid_power_w=-1800), START)
    boosted = ChargeWiseController(ControllerConfig(solar_start_confirmation_s=0)).evaluate(
        SOLAR,
        _readings(grid_power_w=-1800, ev_first_boost_w=2400),
        START,
    )

    assert plain.requested_current_a == 7
    assert plain.reason is ChargeWiseReason.SOLAR_CHARGING
    assert boosted.requested_current_a == 17
    assert boosted.reason is ChargeWiseReason.EV_FIRST
    assert boosted.available_solar_w == 4200


def test_ev_first_forecast_gate_pauses_solar_charging() -> None:
    """The EV waits when forecast surplus cannot cover the battery's remaining need."""
    decision = ChargeWiseController(ControllerConfig()).evaluate(
        SOLAR,
        _readings(grid_power_w=-7200, ev_first_blocked=True),
        START,
    )

    assert decision.status is ControllerStatus.WAITING
    assert decision.reason is ChargeWiseReason.EV_FIRST_WAITING
    assert decision.requested_current_a == 0
    assert not decision.charger_enabled
    assert decision.available_solar_w == 7200


def _running(**config: int) -> ChargeWiseController:
    return ChargeWiseController(ControllerConfig(smoothing_window_s=0, solar_start_confirmation_s=0, **config))


def test_settle_hold_blocks_further_changes_until_the_charger_catches_up() -> None:
    """A second adjustment inside the hold keeps the current set, then follows once it ends."""
    controller = _running(settle_hold_s=30)
    first = controller.evaluate(SOLAR, _readings(grid_power_w=-2400), START)
    assert first.requested_current_a == 10

    held = controller.evaluate(
        SOLAR,
        _readings(charger_enabled=True, current_target_a=10, charger_power_w=0, grid_power_w=-4800),
        START + timedelta(seconds=10),
    )
    assert held.requested_current_a == 10
    assert held.next_update_at == START + timedelta(seconds=30)

    after = controller.evaluate(
        SOLAR,
        _readings(charger_enabled=True, current_target_a=10, charger_power_w=2400, grid_power_w=-2400),
        START + timedelta(seconds=30),
    )
    assert after.requested_current_a == 20


def test_settle_hold_does_not_delay_battery_protection() -> None:
    """Battery protection reductions apply immediately even during the hold."""
    controller = _running(settle_hold_s=300, battery_confirmation_s=0)
    controller.evaluate(SOLAR, _readings(grid_power_w=-4800), START)
    controller.evaluate(
        SOLAR,
        _readings(
            charger_enabled=True, current_target_a=20, charger_power_w=4800, grid_power_w=0, battery_discharge_w=480
        ),
        START + timedelta(seconds=1),
    )
    decision = controller.evaluate(
        SOLAR,
        _readings(
            charger_enabled=True, current_target_a=20, charger_power_w=4800, grid_power_w=0, battery_discharge_w=480
        ),
        START + timedelta(seconds=2),
    )
    assert decision.requested_current_a < 20


def test_smoothing_ignores_a_brief_spike_in_house_load() -> None:
    """A short drop in the budget barely moves the target; a sustained one does."""
    controller = ChargeWiseController(ControllerConfig(settle_hold_s=0, smoothing_window_s=60))
    steady = _readings(charger_enabled=True, current_target_a=20, charger_power_w=4800, grid_power_w=0)
    controller.evaluate(SOLAR, steady, START)
    controller.evaluate(SOLAR, steady, START + timedelta(seconds=50))
    spike = controller.evaluate(
        SOLAR,
        _readings(charger_enabled=True, current_target_a=20, charger_power_w=4800, grid_power_w=3000),
        START + timedelta(seconds=55),
    )
    assert spike.requested_current_a >= 19

    sustained = controller.evaluate(
        SOLAR,
        _readings(charger_enabled=True, current_target_a=20, charger_power_w=4800, grid_power_w=3000),
        START + timedelta(seconds=200),
    )
    assert sustained.requested_current_a == 7
