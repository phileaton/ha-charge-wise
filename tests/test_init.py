"""Tests for Charge Wise config-entry setup and cleanup."""

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


async def test_manual_mode_enables_the_charger(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Manual mode sends the selected switch command and reports charging."""

    async def turn_on(call: ServiceCall) -> None:
        hass.states.async_set(call.data["entity_id"], "on")

    hass.services.async_register("switch", "turn_on", turn_on)
    mode_entity = er.async_get(hass).async_get_entity_id(
        "select",
        DOMAIN,
        f"{init_integration.entry_id}_mode",
    )
    assert mode_entity is not None

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": mode_entity, "option": "manual"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("switch.charger_enable").state == "on"
    status_entity = er.async_get(hass).async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{init_integration.entry_id}_controller_status",
    )
    assert status_entity is not None
    assert hass.states.get(status_entity).state == "charging"


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
