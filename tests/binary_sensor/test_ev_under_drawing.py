"""Verify current shortfall warnings through Home Assistant entities and timers."""

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.charge_wise.const import CONF_CHARGER_CURRENT_ENTITY, DOMAIN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

pytestmark = pytest.mark.integration


async def _start(hass: HomeAssistant, entry: MockConfigEntry, measured: str = "13") -> str:
    """Start a real entry with a charger accepting and reporting its commanded limit."""
    hass.states.async_set("sensor.measured_current", measured, {"unit_of_measurement": "A"})
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_CHARGER_CURRENT_ENTITY: "sensor.measured_current"}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async def set_limit(call: ServiceCall) -> None:
        hass.states.async_set("number.current_limit", str(call.data["value"]), {"unit_of_measurement": "A"})

    async def switch_on(call: ServiceCall) -> None:
        hass.states.async_set("switch.charger_enable", "on")

    hass.services.async_register("number", "set_value", set_limit)
    hass.services.async_register("switch", "turn_on", switch_on)
    coordinator = entry.runtime_data.coordinator
    await coordinator.async_set_manual_current(22)
    await coordinator.async_set_switch("enabled", True)
    await coordinator.async_set_switch("manual_override", True)
    hass.states.async_set("sensor.charger_power", "3000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_ev_under_drawing")
    assert entity_id is not None
    return entity_id


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int) -> None:
    """Let real scheduled callbacks fire without requiring a source state change."""
    freezer.tick(seconds)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_warning_confirmation_and_recovery(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Five continuous minutes trigger the warning; recovery takes one continuous minute."""
    entity_id = await _start(hass, config_entry)
    assert hass.states.get(entity_id).state == "off"
    await _advance(hass, freezer, 299)
    assert hass.states.get(entity_id).state == "off"
    await _advance(hass, freezer, 2)
    assert hass.states.get(entity_id).state == "on"
    assert hass.states.get(entity_id).attributes["device_class"] == "problem"

    hass.states.async_set("sensor.measured_current", "21", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    await _advance(hass, freezer, 59)
    assert hass.states.get(entity_id).state == "on"
    hass.states.async_set("sensor.measured_current", "13", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    await _advance(hass, freezer, 2)
    assert hass.states.get(entity_id).state == "on"
    hass.states.async_set("sensor.measured_current", "21", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    await _advance(hass, freezer, 61)
    assert hass.states.get(entity_id).state == "off"


@pytest.mark.parametrize("measured", ["18", "21", "22"])
async def test_small_shortfalls_do_not_warn(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, measured: str
) -> None:
    """A draw within twenty percent of the offered limit never triggers."""
    entity_id = await _start(hass, config_entry, measured)
    await _advance(hass, freezer, 600)
    assert hass.states.get(entity_id).state == "off"


@pytest.mark.parametrize(("offered", "measured", "expected"), [(6, "4.5", "off"), (10, "8", "on")])
async def test_absolute_and_percentage_thresholds(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    offered: int,
    measured: str,
    expected: str,
) -> None:
    """Both thresholds must be met, including their exact boundaries."""
    entity_id = await _start(hass, config_entry, measured)
    await config_entry.runtime_data.coordinator.async_set_manual_current(offered)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 301)
    assert hass.states.get(entity_id).state == expected


async def test_wrong_current_unit_is_not_used(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """A sensor reporting power must never be interpreted as measured amperes."""
    entity_id = await _start(hass, config_entry)
    hass.states.async_set("sensor.measured_current", "13", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await _advance(hass, freezer, 301)
    assert hass.states.get(entity_id).state == "unknown"


@pytest.mark.parametrize("invalid", ["unavailable", "unknown", "nan", "inf", "-1"])
async def test_invalid_measurements_clear_and_restart_confirmation(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory, invalid: str
) -> None:
    """Missing or invalid current suppresses the warning and discards elapsed confirmation."""
    entity_id = await _start(hass, config_entry)
    await _advance(hass, freezer, 301)
    assert hass.states.get(entity_id).state == "on"
    hass.states.async_set("sensor.measured_current", invalid, {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
    hass.states.async_set("sensor.measured_current", "13", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    await _advance(hass, freezer, 299)
    assert hass.states.get(entity_id).state == "off"
    await _advance(hass, freezer, 2)
    assert hass.states.get(entity_id).state == "on"


async def test_interrupted_shortfall_and_charging_end(
    hass: HomeAssistant, config_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Brief gaps do not accumulate; ending a session clears an active warning immediately."""
    entity_id = await _start(hass, config_entry)
    await _advance(hass, freezer, 240)
    hass.states.async_set("sensor.measured_current", "21", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    hass.states.async_set("sensor.measured_current", "13", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    await _advance(hass, freezer, 61)
    assert hass.states.get(entity_id).state == "off"
    await _advance(hass, freezer, 240)
    assert hass.states.get(entity_id).state == "on"
    hass.states.async_set("sensor.charger_power", "0", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"


async def test_warning_requires_a_configured_current_sensor(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Power readings alone do not create the optional warning entity."""
    assert (
        er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, f"{init_integration.entry_id}_ev_under_drawing")
        is None
    )
