"""Privacy checks for diagnostics served by Home Assistant."""

import json

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.core import HomeAssistant


# Home Assistant 2026.10's HTTP server uses legacy string application and request keys.
@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.(AppKey|RequestKey) instances for keys:"
    "aiohttp.web_exceptions.NotAppKeyWarning:homeassistant.components.http"
)
async def test_diagnostics_redacts_vehicle_names_and_entity_references(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: MockConfigEntry,
) -> None:
    """Keep personal names and source IDs private while retaining useful control settings."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={"refresh_token": "private-token", "location": {"latitude": 12.345}},
        options={
            **config_entry.options,
            "vehicles": [
                {
                    "id": "private-vehicle-id",
                    "name": "Alice's Rivian",
                    "battery_entity": "sensor.alice_rivian_battery",
                    "battery_capacity_kwh": 135,
                }
            ],
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    exported = json.dumps(result)
    for private in ("private-token", "12.345", "private-vehicle-id", "Alice", "alice_rivian", "sensor.grid_power"):
        assert private not in exported
    assert result["entry"]["options"]["maximum_current_a"] == 32
    assert result["entry"]["options"]["vehicles"][0]["battery_capacity_kwh"] == 135
    assert result["coordinator"]["data"]["status"] == "off"
    assert result["coordinator"]["data"]["vehicle_connected"] is True
    assert result["coordinator"]["data"]["charger_connection_source"] == "**REDACTED**"
