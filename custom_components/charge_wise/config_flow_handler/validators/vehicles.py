"""Validate source readings for display-only vehicles."""

from typing import Any

from custom_components.charge_wise.config_flow_handler.schemas.vehicles import VEHICLE_FIELDS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def validate_vehicle(hass: HomeAssistant, values: dict[str, Any]) -> dict[str, str]:
    """Check selected domains and units without requiring a vehicle to be awake."""
    errors: dict[str, str] = {}
    if not values.get("name", "").strip():
        errors["name"] = "vehicle_name_required"
    registry = er.async_get(hass)
    for key, (domains, units) in VEHICLE_FIELDS.items():
        entity_id = values.get(key)
        if not entity_id:
            if key == "battery_entity":
                errors[key] = "vehicle_entity_required"
            continue
        state = hass.states.get(entity_id)
        registered = registry.async_get(entity_id)
        if entity_id.split(".", 1)[0] not in domains or (state is None and registered is None):
            errors[key] = "vehicle_invalid_entity"
            continue
        unit = state.attributes.get("unit_of_measurement") if state else None
        if unit is None and registered is not None:
            unit = registered.unit_of_measurement
        if units and unit not in units:
            errors[key] = "vehicle_invalid_unit"
    return errors
