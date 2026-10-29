"""Set up the sensor platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.sensor.controller import ENTITY_DESCRIPTIONS
from custom_components.charge_wise.sensor.entity import ChargeWiseSensor

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
    """Set up the controller sensors."""
    async_add_entities(
        ChargeWiseSensor(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
