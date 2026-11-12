"""Set up the binary sensor platform."""

from typing import TYPE_CHECKING

from custom_components.charge_wise.binary_sensor.battery_protection import (
    ENTITY_DESCRIPTION,
    ChargeWiseBatteryProtectionBinarySensor,
)
from custom_components.charge_wise.binary_sensor.charging_not_detected import (
    ENTITY_DESCRIPTION as NOT_DETECTED_DESCRIPTION,
    ChargeWiseChargingNotDetectedBinarySensor,
)
from custom_components.charge_wise.binary_sensor.ev_first_active import (
    ENTITY_DESCRIPTION as EV_FIRST_DESCRIPTION,
    ChargeWiseEvFirstActiveBinarySensor,
)
from custom_components.charge_wise.binary_sensor.ev_under_drawing import (
    ENTITY_DESCRIPTION as UNDER_DRAWING_DESCRIPTION,
    ChargeWiseEvUnderDrawingBinarySensor,
)
from custom_components.charge_wise.binary_sensor.offpeak_active import (
    ENTITY_DESCRIPTION as OFFPEAK_DESCRIPTION,
    ChargeWiseOffpeakActiveBinarySensor,
)
from custom_components.charge_wise.binary_sensor.vehicle_charging import (
    ENTITY_DESCRIPTION as CHARGING_DESCRIPTION,
    ChargeWiseVehicleChargingBinarySensor,
)
from custom_components.charge_wise.binary_sensor.vehicle_connected import (
    ENTITY_DESCRIPTION as CONNECTED_DESCRIPTION,
    ChargeWiseVehicleConnectedBinarySensor,
)
from custom_components.charge_wise.const import CONF_CHARGER_CURRENT_ENTITY, DOMAIN
from homeassistant.helpers import entity_registry as er

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
    """Create controller observations and configured protection diagnostics."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.options.get(CONF_CHARGER_CURRENT_ENTITY):
        async_add_entities([ChargeWiseEvUnderDrawingBinarySensor(coordinator, UNDER_DRAWING_DESCRIPTION)])
    async_add_entities(
        [
            ChargeWiseChargingNotDetectedBinarySensor(coordinator, NOT_DETECTED_DESCRIPTION),
            ChargeWiseVehicleConnectedBinarySensor(coordinator, CONNECTED_DESCRIPTION),
            ChargeWiseVehicleChargingBinarySensor(coordinator, CHARGING_DESCRIPTION),
            ChargeWiseOffpeakActiveBinarySensor(coordinator, OFFPEAK_DESCRIPTION),
            ChargeWiseEvFirstActiveBinarySensor(coordinator, EV_FIRST_DESCRIPTION),
        ],
    )
    if coordinator.battery_configured:
        async_add_entities(
            [ChargeWiseBatteryProtectionBinarySensor(coordinator, ENTITY_DESCRIPTION)],
        )
        return

    registry = er.async_get(hass)
    stale_entity_id = registry.async_get_entity_id(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_{ENTITY_DESCRIPTION.key}",
    )
    if stale_entity_id is not None:
        registry.async_remove(stale_entity_id)
