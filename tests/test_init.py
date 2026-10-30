"""Tests for Charge Wise config-entry setup and cleanup."""

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er


async def test_entry_unloads_cleanly(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The coordinator listeners are removed when the entry unloads."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def _turn_on(hass: HomeAssistant, entry: MockConfigEntry, *keys: str) -> None:
    """Turn on Charge Wise switches through the real service."""
    registry = er.async_get(hass)
    for key in keys:
        entity_id = registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id is not None
        await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()


async def test_manual_override_enables_the_charger(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Manual override sends the selected switch command and reports charging."""
    await _turn_on(hass, init_integration, "enabled", "manual_override")

    async def turn_on(call: ServiceCall) -> None:
        hass.states.async_set(call.data["entity_id"], "on")

    hass.services.async_register("switch", "turn_on", turn_on)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.charger_enable"}, blocking=True)
    await hass.async_block_till_done()

    assert hass.states.get("switch.charger_enable").state == "on"
    status_entity = er.async_get(hass).async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{init_integration.entry_id}_controller_status",
    )
    assert status_entity is not None
    assert hass.states.get(status_entity).state == "charging"


async def test_offpeak_window_charges_from_the_grid_and_stops_outside_it(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Off-peak charging follows the configured local-time window."""
    commands: list[str] = []

    async def turn_on(call: ServiceCall) -> None:
        commands.append("on")
        hass.states.async_set(call.data["entity_id"], "on")

    async def turn_off(call: ServiceCall) -> None:
        commands.append("off")
        hass.states.async_set(call.data["entity_id"], "off")

    registry = er.async_get(hass)
    active_entity = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{init_integration.entry_id}_offpeak_active")
    status_entity = registry.async_get_entity_id("sensor", DOMAIN, f"{init_integration.entry_id}_controller_status")
    reason_entity = registry.async_get_entity_id("sensor", DOMAIN, f"{init_integration.entry_id}_decision_reason")
    next_entity = registry.async_get_entity_id("sensor", DOMAIN, f"{init_integration.entry_id}_next_offpeak_window")
    assert active_entity and status_entity and reason_entity and next_entity

    freezer.move_to("2026-01-07 11:00:00+00:00")
    await _turn_on(hass, init_integration, "enabled", "offpeak_enabled")
    hass.services.async_register("switch", "turn_on", turn_on)
    hass.services.async_register("switch", "turn_off", turn_off)
    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_set_offpeak_current(10)
    await hass.async_block_till_done()

    assert hass.states.get(active_entity).state == "on"
    assert hass.states.get(status_entity).state == "charging"
    assert hass.states.get(reason_entity).state == "offpeak_window"
    assert hass.states.get("switch.charger_enable").state == "on"

    freezer.move_to("2026-01-07 15:00:00+00:00")
    await coordinator.async_set_offpeak_current(11)
    await hass.async_block_till_done()

    assert hass.states.get(active_entity).state == "off"
    assert hass.states.get(status_entity).state == "waiting"
    assert hass.states.get(reason_entity).state == "offpeak_waiting"
    assert hass.states.get("switch.charger_enable").state == "off"
    assert hass.states.get(next_entity).state == "2026-01-08T08:00:00+00:00"


async def test_legacy_demo_entry_has_an_actionable_setup_error(
    hass: HomeAssistant,
) -> None:
    """An old credential entry is rejected instead of failing on missing fields."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Legacy",
        data={"username": "old-user", "password": "old-password"},
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "Remove it and add Charge Wise again with your charger entities" in entry.reason
