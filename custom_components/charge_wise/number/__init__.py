"""Set up the number platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.number.manual_current import ENTITY_DESCRIPTION, ChargeWiseManualCurrentNumber

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
    """Set up the manual-current number entity."""
    async_add_entities(
        [ChargeWiseManualCurrentNumber(entry.runtime_data.coordinator, ENTITY_DESCRIPTION)],
    )
