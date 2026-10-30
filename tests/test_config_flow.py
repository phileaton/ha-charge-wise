"""Tests for the entity-based Charge Wise config flow."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import CONF_OFFPEAK_WINDOWS, DOMAIN
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
        user_input={k: v for k, v in config_entry.options.items() if k != CONF_OFFPEAK_WINDOWS},
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
        user_input={k: v for k, v in config_entry.options.items() if k != CONF_OFFPEAK_WINDOWS},
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "already_configured"}


async def test_offpeak_windows_are_stored_as_a_list(hass, config_entry) -> None:
    """Flat window form fields are collapsed into the stored window list."""
    config_entry.add_to_hass(hass)
    user_input = {k: v for k, v in config_entry.options.items() if k != CONF_OFFPEAK_WINDOWS}
    user_input |= {
        "offpeak_window_1_start": "23:00:00",
        "offpeak_window_1_end": "06:00:00",
        "offpeak_window_1_days": "weekdays",
    }

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input=user_input)

    assert result["data"][CONF_OFFPEAK_WINDOWS] == [{"start": "23:00", "end": "06:00", "days": "weekdays"}]


async def test_incomplete_offpeak_window_is_rejected(hass, config_entry) -> None:
    """A window with only a start time shows an error."""
    config_entry.add_to_hass(hass)
    user_input = {k: v for k, v in config_entry.options.items() if k != CONF_OFFPEAK_WINDOWS}
    user_input["offpeak_window_1_start"] = "23:00:00"

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input=user_input)

    assert result["errors"] == {"base": "offpeak_window_incomplete"}
