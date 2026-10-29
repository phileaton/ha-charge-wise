"""Set up the binary sensor platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.binary_sensor.battery_protection import (
    ENTITY_DESCRIPTION,
    ChargeWiseBatteryProtectionBinarySensor,
)

PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from custom_components.charge_wise.data import ChargeWiseConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargeWiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the battery-protection entity when its source is configured."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.battery_configured:
        async_add_entities(
            [ChargeWiseBatteryProtectionBinarySensor(coordinator, ENTITY_DESCRIPTION)],
        )
