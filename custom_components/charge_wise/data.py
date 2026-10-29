"""
Runtime data types for charge_wise.

Access pattern: entry.runtime_data.client / entry.runtime_data.coordinator
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import ChargeWiseApiClient
    from .coordinator import ChargeWiseDataUpdateCoordinator


type ChargeWiseConfigEntry = ConfigEntry[ChargeWiseData]


@dataclass
class ChargeWiseData:
    """Runtime data stored on the config entry after a successful setup."""

    client: ChargeWiseApiClient
    coordinator: ChargeWiseDataUpdateCoordinator
    integration: Integration
