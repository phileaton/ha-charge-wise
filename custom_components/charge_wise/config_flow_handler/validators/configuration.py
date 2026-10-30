"""Validation shared by the config and options flows."""

from typing import Any

from custom_components.charge_wise.config_flow_handler.schemas.windows import validate_windows
from custom_components.charge_wise.const import (
    CONF_BATTERY_DISCHARGE_W,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_RECOVERY_W,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_EV_CONNECTED_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    CONF_MAXIMUM_CURRENT_A,
    CONF_MINIMUM_CURRENT_A,
    DOMAIN,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant

_REQUIRED_ENTITY_DOMAINS = {
    CONF_GRID_POWER_ENTITY: "sensor",
    CONF_CHARGER_POWER_ENTITY: "sensor",
    CONF_CHARGER_SWITCH_ENTITY: "switch",
    CONF_CURRENT_TARGET_ENTITY: "number",
}
_OPTIONAL_ENTITY_DOMAINS = {
    CONF_HARDWARE_MAXIMUM_ENTITY: "number",
    CONF_BATTERY_POWER_ENTITY: "sensor",
    CONF_EV_CONNECTED_ENTITY: "binary_sensor",
}
_POWER_SENSOR_KEYS = {
    CONF_GRID_POWER_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
}
_POWER_UNITS = {
    UnitOfPower.MILLIWATT,
    UnitOfPower.WATT,
    UnitOfPower.KILO_WATT,
}


def validate_configuration(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    *,
    current_entry_id: str | None = None,
) -> dict[str, str]:
    """Validate selected entity IDs, power units, mappings, and current limits."""
    for key, domain in _REQUIRED_ENTITY_DOMAINS.items():
        entity_id = user_input.get(key)
        if not entity_id:
            return {"base": "entity_required"}
        if entity_id.split(".", maxsplit=1)[0] != domain:
            return {"base": "invalid_entity"}
        if hass.states.get(entity_id) is None:
            return {"base": "entity_not_found"}

    for key, domain in _OPTIONAL_ENTITY_DOMAINS.items():
        entity_id = user_input.get(key)
        if not entity_id:
            continue
        if entity_id.split(".", maxsplit=1)[0] != domain:
            return {"base": "invalid_entity"}
        if hass.states.get(entity_id) is None:
            return {"base": "entity_not_found"}

    for key in _POWER_SENSOR_KEYS:
        entity_id = user_input.get(key)
        if entity_id is None:
            continue
        state = hass.states.get(entity_id)
        if state is not None and state.attributes.get("unit_of_measurement") not in _POWER_UNITS:
            return {"base": "invalid_power_unit"}

    if user_input.get(CONF_HARDWARE_MAXIMUM_ENTITY) == user_input[CONF_CURRENT_TARGET_ENTITY]:
        return {"base": "invalid_entity"}

    minimum = int(user_input[CONF_MINIMUM_CURRENT_A])
    maximum = int(user_input[CONF_MAXIMUM_CURRENT_A])
    if minimum > maximum:
        return {"base": "invalid_limits"}

    if int(user_input[CONF_BATTERY_RECOVERY_W]) >= int(user_input[CONF_BATTERY_DISCHARGE_W]):
        return {"base": "invalid_battery_thresholds"}

    hardware_entity = user_input.get(CONF_HARDWARE_MAXIMUM_ENTITY)
    if hardware_entity:
        hardware_state = hass.states.get(hardware_entity)
        if hardware_state is not None and hardware_state.state not in ("unknown", "unavailable"):
            try:
                hardware_maximum = float(hardware_state.state)
            except ValueError:
                return {"base": "invalid_hardware_limit"}
            if hardware_maximum < minimum:
                return {"base": "invalid_hardware_limit"}

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == current_entry_id:
            continue
        if any(
            user_input.get(key) == entry.options.get(key)
            for key in (CONF_CHARGER_SWITCH_ENTITY, CONF_CURRENT_TARGET_ENTITY)
        ):
            return {"base": "already_configured"}

    return validate_windows(user_input)
