"""Set up Charge Wise as an event-driven Home Assistant integration."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.const import (
    CONF_BATTERY_DISCHARGE_SIGN,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_MAXIMUM_CURRENT_A,
    DOMAIN,
)
from custom_components.charge_wise.coordinator import ChargeWiseDataUpdateCoordinator
from custom_components.charge_wise.data import ChargeWiseData
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from custom_components.charge_wise.data import ChargeWiseConfigEntry

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

_REQUIRED_OPTIONS = (
    CONF_GRID_POWER_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_MAXIMUM_CURRENT_A,
    CONF_BATTERY_DISCHARGE_SIGN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargeWiseConfigEntry,
) -> bool:
    """Set up an entity-driven charger controller."""
    if any(key not in entry.options for key in _REQUIRED_OPTIONS):
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="legacy_entry",
        )

    registry = er.async_get(hass)
    if stale_mode := registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_mode"):
        registry.async_remove(stale_mode)

    coordinator = ChargeWiseDataUpdateCoordinator(hass, entry)
    entry.runtime_data = ChargeWiseData(coordinator=coordinator)
    entry.async_on_unload(coordinator.async_stop)
    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ChargeWiseConfigEntry,
) -> bool:
    """Unload the integration platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload the integration after its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
