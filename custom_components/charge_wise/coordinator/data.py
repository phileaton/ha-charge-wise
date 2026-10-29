"""Typed coordinator and controller data for Charge Wise."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from custom_components.charge_wise.utils.charging_controller import ChargeWiseMode, ChargeWiseReason, ControllerStatus

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .base import ChargeWiseDataUpdateCoordinator


type ChargeWiseConfigEntry = ConfigEntry[ChargeWiseData]


@dataclass(frozen=True)
class ChargeWiseSnapshot:
    """Values published to platform entities."""

    mode: ChargeWiseMode
    status: ControllerStatus
    reason: ChargeWiseReason
    available_solar_w: float | None
    requested_current_a: float
    manual_current_a: float
    battery_protection_active: bool | None


@dataclass
class ChargeWiseData:
    """Runtime data stored on a config entry."""

    coordinator: ChargeWiseDataUpdateCoordinator
