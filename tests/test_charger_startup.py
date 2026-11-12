"""Verify startup failures through real entity services and timed state updates."""

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    setup_test_component_platform,
)

from custom_components.charge_wise.const import DOMAIN
from homeassistant.components.number import NumberEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component


class CurrentTarget(NumberEntity):
    """Simulate a charger that can delay confirmation of its current limit."""

    _attr_name = "Current Limit"
    _attr_unique_id = "startup_current"
    _attr_native_value = 6
    _attr_native_unit_of_measurement = "A"
    _attr_native_min_value = 6
    _attr_native_max_value = 32
    _attr_native_step = 1

    def __init__(self) -> None:
        """Track requested limits and delayed replies."""
        self.commands: list[float] = []
        self.delay = False

    async def async_set_native_value(self, value: float) -> None:
        """Optionally publish the accepted limit."""
        self.commands.append(value)
        if not self.delay:
            self._attr_native_value = value
            self.async_write_ha_state()

    def confirm(self, value: float) -> None:
        """Publish a delayed acknowledgement from the charger."""
        self._attr_native_value = value
        self.async_write_ha_state()

    def set_available(self, available: bool) -> None:
        """Expose or hide a transaction-dependent session limit."""
        self._attr_available = available
        self.async_write_ha_state()


class ChargerSwitch(SwitchEntity):
    """Simulate a charger with optional delayed start confirmation."""

    _attr_name = "Charger Enable"
    _attr_unique_id = "startup_switch"
    _attr_is_on = False

    def __init__(self) -> None:
        """Track commands without assuming a start draws power."""
        self.starts = 0
        self.stops = 0
        self.delay = False

    async def async_turn_on(self, **kwargs: object) -> None:
        """Optionally confirm a start request."""
        self.starts += 1
        if not self.delay:
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        """Confirm the safety stop."""
        self.stops += 1
        self._attr_is_on = False
        self.async_write_ha_state()


@pytest.fixture
async def startup_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> tuple[MockConfigEntry, CurrentTarget, ChargerSwitch]:
    """Load the integration with real source number and switch platforms."""
    target = CurrentTarget()
    charger = ChargerSwitch()
    hass.states.async_remove("number.current_limit")
    hass.states.async_remove("switch.charger_enable")
    setup_test_component_platform(hass, "number", [target])
    setup_test_component_platform(hass, "switch", [charger])
    assert await async_setup_component(hass, "number", {"number": [{"platform": "test"}]})
    assert await async_setup_component(hass, "switch", {"switch": [{"platform": "test"}]})
    hass.states.async_set("sensor.charger_status", "Preparing")
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            "charger_status_entity": "sensor.charger_status",
            "charger_status_profile": "ocpp",
            "cooldown_s": 0,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry, target, charger


def _entity(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id
    return entity_id


async def _start(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    for key in ("enabled", "manual_override"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": _entity(hass, entry, "switch", key)}, blocking=True
        )
    await hass.async_block_till_done()


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int) -> None:
    freezer.tick(seconds)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_current_limit_requires_confirmation_and_latches_failure(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
) -> None:
    """An ignored current command never enables charging or retries indefinitely."""
    entry, target, charger = startup_entry
    target.delay = True
    await _start(hass, entry)
    assert target.commands == [32]
    assert charger.starts == 0
    for power in (-1000, -1100, -1200):
        hass.states.async_set("sensor.grid_power", power, {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
    assert target.commands == [32]
    await _advance(hass, freezer, 31)
    assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == "error"
    target.delay = False
    await _advance(hass, freezer, 300)
    hass.states.async_set("sensor.grid_power", "-1500", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert charger.starts == 0
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": _entity(hass, entry, "switch", "enabled")}, blocking=True
    )
    await _start(hass, entry)
    assert charger.starts == 1
    assert hass.states.get("number.current_limit").state == "32.0"


@pytest.mark.parametrize("recovers", [True, False])
async def test_transaction_limit_must_become_available_within_grace(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
    recovers: bool,
) -> None:
    """Allow session-dependent OCPP limits to appear, but stop if they never do."""
    entry, target, charger = startup_entry
    target.set_available(False)
    await hass.async_block_till_done()
    await _start(hass, entry)
    assert charger.starts == 1
    assert target.commands == []
    await _advance(hass, freezer, 10)
    target.set_available(recovers)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 21)
    expected = "charging" if recovers else "error"
    assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == expected
    assert hass.states.get("switch.charger_enable").state == ("on" if recovers else "off")
    assert target.commands == ([32] if recovers else [])


async def test_ignored_start_command_is_bounded(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A charger that never confirms its switch is not sent endless start commands."""
    entry, _, charger = startup_entry
    charger.delay = True
    await _start(hass, entry)
    assert charger.starts == 1
    await _advance(hass, freezer, 31)
    assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == "error"
    await _advance(hass, freezer, 300)
    assert charger.starts == 1


@pytest.mark.parametrize(
    ("session", "power", "expected"),
    [
        ("Preparing", "0", "error"),
        ("Charging", "500", "charging"),
        ("SuspendedEV", "0", "charging"),
        ("Finishing", "0", "charging"),
    ],
)
async def test_start_requires_power_except_for_explicit_paused_or_finished_sessions(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
    session: str,
    power: str,
    expected: str,
) -> None:
    """Measure actual charging without treating explicit vehicle pauses as start failures."""
    entry, _, _ = startup_entry
    hass.states.async_set("sensor.charger_status", session)
    hass.states.async_set("sensor.charger_power", power, {"unit_of_measurement": "W"})
    await _start(hass, entry)
    await _advance(hass, freezer, 301)
    assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == expected
    assert hass.states.get("switch.charger_enable").state == "on"


async def test_confirmed_current_adjustments_do_not_accumulate_a_timeout(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A responsive charger may keep accepting new targets for longer than the command grace."""
    entry, _, _ = startup_entry
    hass.states.async_set("sensor.charger_power", "2000", {"unit_of_measurement": "W"})
    await _start(hass, entry)
    for current in (10, 12, 14, 16):
        await _advance(hass, freezer, 10)
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _entity(hass, entry, "number", "manual_current"), "value": current},
            blocking=True,
        )
        await hass.async_block_till_done()
        assert float(hass.states.get("number.current_limit").state) == current
        assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == "charging"
    assert hass.states.get("switch.charger_enable").state == "on"


async def test_generic_unavailable_current_target_never_enables_charging(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Only an explicitly identified OCPP transaction can bootstrap with an unavailable limit."""
    entry, target, charger = startup_entry
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "charger_status_entity": "binary_sensor.ev_connected"}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    target.set_available(False)
    await hass.async_block_till_done()
    await _start(hass, entry)
    assert charger.starts == 0
    await _advance(hass, freezer, 31)
    assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == "error"
    assert charger.starts == 0


async def test_unconfirmed_current_change_stops_until_the_charger_acknowledges(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A delayed reduction cannot leave the charger drawing at its previous higher limit."""
    entry, target, charger = startup_entry
    hass.states.async_set("sensor.charger_power", "2000", {"unit_of_measurement": "W"})
    await _start(hass, entry)
    target.delay = True
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _entity(hass, entry, "number", "manual_current"), "value": 16},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.charger_enable").state == "off"
    assert target.commands == [32, 16]
    await _advance(hass, freezer, 10)
    target.confirm(16)
    await hass.async_block_till_done()
    assert charger.starts == 2
    assert hass.states.get("switch.charger_enable").state == "on"
    assert hass.states.get(_entity(hass, entry, "sensor", "controller_status")).state == "charging"


async def test_no_power_error_keeps_charging_enabled_and_recovers_automatically(
    hass: HomeAssistant,
    startup_entry: tuple[MockConfigEntry, CurrentTarget, ChargerSwitch],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Report a failed start without stopping, repeating commands, or requiring a manual reset."""
    entry, target, charger = startup_entry
    await _start(hass, entry)
    await _advance(hass, freezer, 301)
    status = _entity(hass, entry, "sensor", "controller_status")
    assert hass.states.get(status).state == "error"
    assert hass.states.get("switch.charger_enable").state == "on"
    assert hass.states.get(_entity(hass, entry, "switch", "enabled")).state == "on"
    await _advance(hass, freezer, 600)
    hass.states.async_set("sensor.grid_power", "-500", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert charger.starts == 1
    assert charger.stops == 0
    assert target.commands == [32]
    hass.states.async_set("sensor.charger_power", "2000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "charging"
    assert hass.states.get("switch.charger_enable").state == "on"
