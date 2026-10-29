"""Tests for the entity-based Charge Wise config flow."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import DOMAIN
from homeassistant.core import HomeAssistant


async def test_config_flow_stores_entity_mappings_in_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """A valid setup creates an entry without credentials or network access."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=config_entry.options,
    )

    assert result["type"] == "create_entry"
    assert result["data"] == {}
    assert result["options"]["grid_power_entity"] == "sensor.grid_power"
    assert "username" not in result["options"]
    assert "password" not in result["options"]


async def test_config_flow_rejects_reused_charger_controls(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Charger switches and current targets cannot be claimed by two entries."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=config_entry.options,
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "already_configured"}
