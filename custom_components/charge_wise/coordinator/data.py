"""Typed coordinator and controller data for Charge Wise."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from custom_components.charge_wise.utils.charging_controller import ChargeWiseReason, ControllerStatus

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .base import ChargeWiseDataUpdateCoordinator


type ChargeWiseConfigEntry = ConfigEntry[ChargeWiseData]


@dataclass(frozen=True)
class ChargeWiseSnapshot:
    """Values published to platform entities."""

    enabled: bool
    solar_enabled: bool
    offpeak_enabled: bool
    manual_override: bool
    ev_first_enabled: bool
    ev_first_active: bool
    offpeak_active: bool
    next_offpeak_start: datetime | None
    status: ControllerStatus
    reason: ChargeWiseReason
    available_solar_w: float | None
    requested_current_a: float
    manual_current_a: float
    offpeak_current_a: float
    battery_protection_active: bool | None
    average_house_load_w: float | None = None


@dataclass
class ChargeWiseData:
    """Runtime data stored on a config entry."""

    coordinator: ChargeWiseDataUpdateCoordinator
