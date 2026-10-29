"""Config-entry typing for Charge Wise runtime data."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.coordinator.data import ChargeWiseData

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

type ChargeWiseConfigEntry = ConfigEntry[ChargeWiseData]
