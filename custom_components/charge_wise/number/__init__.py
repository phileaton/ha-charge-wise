"""Set up the number platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.number.manual_current import (
    ENTITY_DESCRIPTION as MANUAL_DESCRIPTION,
    ChargeWiseManualCurrentNumber,
)
from custom_components.charge_wise.number.offpeak_current import (
    ENTITY_DESCRIPTION as OFFPEAK_DESCRIPTION,
    ChargeWiseOffpeakCurrentNumber,
)

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
    """Set up the manual and off-peak current number entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            ChargeWiseManualCurrentNumber(coordinator, MANUAL_DESCRIPTION),
            ChargeWiseOffpeakCurrentNumber(coordinator, OFFPEAK_DESCRIPTION),
        ],
    )
