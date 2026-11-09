"""Set up the select platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.select.ev_first import (
    ENTITY_DESCRIPTIONS as EV_FIRST_DESCRIPTIONS,
    ChargeWiseEvFirstSelect,
)
from custom_components.charge_wise.select.offpeak import ENTITY_DESCRIPTIONS, ChargeWiseOffpeakSelect

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
    """Set up the off-peak and EV-first charging modes."""
    async_add_entities(
        ChargeWiseEvFirstSelect(entry.runtime_data.coordinator, description) for description in EV_FIRST_DESCRIPTIONS
    )
    async_add_entities(
        ChargeWiseOffpeakSelect(entry.runtime_data.coordinator, description) for description in ENTITY_DESCRIPTIONS
    )
