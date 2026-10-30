"""Set up the switch platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.switch.source import ENTITY_DESCRIPTIONS, ChargeWiseSourceSwitch

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from custom_components.charge_wise.data import ChargeWiseConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChargeWiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charging enable and source switches."""
    async_add_entities(
        ChargeWiseSourceSwitch(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
