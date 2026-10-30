"""Per-page validation shared by the config and options flows."""

from collections.abc import Callable, Mapping
from typing import Any

from custom_components.charge_wise.config_flow_handler.schemas.windows import validate_windows
from custom_components.charge_wise.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_DISCHARGE_W,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_RECOVERY_W,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_EV_CONNECTED_ENTITY,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    CONF_MAXIMUM_CURRENT_A,
    CONF_MINIMUM_CURRENT_A,
    CONF_SOLAR_POWER_ENTITY,
    DOMAIN,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant

_REQUIRED_ENTITY_DOMAINS = {
    CONF_GRID_POWER_ENTITY: "sensor",
    CONF_CHARGER_POWER_ENTITY: "sensor",
    CONF_CHARGER_SWITCH_ENTITY: "switch",
    CONF_CURRENT_TARGET_ENTITY: "number",
}
_CHARGER_OPTIONAL_DOMAINS = {
    CONF_HARDWARE_MAXIMUM_ENTITY: "number",
    CONF_EV_CONNECTED_ENTITY: "binary_sensor",
}
_BATTERY_OPTIONAL_DOMAINS = {CONF_BATTERY_POWER_ENTITY: "sensor"}
_FORECAST_OPTIONAL_DOMAINS = {
    CONF_FORECAST_REMAINING_ENTITY: "sensor",
    CONF_BATTERY_LEVEL_ENTITY: "sensor",
    CONF_SOLAR_POWER_ENTITY: "sensor",
}
_EV_FIRST_KEYS = (
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    CONF_BATTERY_CAPACITY_KWH,
)
_ENERGY_UNITS = {
    UnitOfEnergy.WATT_HOUR,
    UnitOfEnergy.KILO_WATT_HOUR,
    UnitOfEnergy.MEGA_WATT_HOUR,
}
_POWER_UNITS = {
    UnitOfPower.MILLIWATT,
    UnitOfPower.WATT,
    UnitOfPower.KILO_WATT,
}

type PageValidator = Callable[..., dict[str, str]]


def _validate_entities(
    hass: HomeAssistant,
    user_input: Mapping[str, Any],
    domains: Mapping[str, str],
    *,
    required: bool,
) -> dict[str, str]:
    """Check that selected entities exist and belong to the expected domain."""
    for key, domain in domains.items():
        entity_id = user_input.get(key)
        if not entity_id:
            if required:
                return {"base": "entity_required"}
            continue
        if entity_id.split(".", maxsplit=1)[0] != domain:
            return {"base": "invalid_entity"}
        if hass.states.get(entity_id) is None:
            return {"base": "entity_not_found"}
    return {}


def _validate_power_units(hass: HomeAssistant, user_input: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, str]:
    """Check that the selected power sensors report a supported unit."""
    for key in keys:
        entity_id = user_input.get(key)
        if entity_id is None:
            continue
        state = hass.states.get(entity_id)
        if state is not None and state.attributes.get("unit_of_measurement") not in _POWER_UNITS:
            return {"base": "invalid_power_unit"}
    return {}


def validate_charger(
    hass: HomeAssistant,
    user_input: Mapping[str, Any],
    *,
    current_entry_id: str | None = None,
) -> dict[str, str]:
    """Validate the charger entities, current limits and that no other entry uses the same controls."""
    if errors := _validate_entities(hass, user_input, _REQUIRED_ENTITY_DOMAINS, required=True):
        return errors
    if errors := _validate_entities(hass, user_input, _CHARGER_OPTIONAL_DOMAINS, required=False):
        return errors
    if errors := _validate_power_units(hass, user_input, (CONF_GRID_POWER_ENTITY, CONF_CHARGER_POWER_ENTITY)):
        return errors

    if user_input.get(CONF_HARDWARE_MAXIMUM_ENTITY) == user_input[CONF_CURRENT_TARGET_ENTITY]:
        return {"base": "invalid_entity"}

    minimum = int(user_input[CONF_MINIMUM_CURRENT_A])
    maximum = int(user_input[CONF_MAXIMUM_CURRENT_A])
    if minimum > maximum:
        return {"base": "invalid_limits"}

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

    return {}


def validate_battery(
    hass: HomeAssistant,
    user_input: Mapping[str, Any],
    **_: Any,
) -> dict[str, str]:
    """Validate the battery power sensor and the protection thresholds."""
    if errors := _validate_entities(hass, user_input, _BATTERY_OPTIONAL_DOMAINS, required=False):
        return errors
    if errors := _validate_power_units(hass, user_input, (CONF_BATTERY_POWER_ENTITY,)):
        return errors
    if int(user_input[CONF_BATTERY_RECOVERY_W]) >= int(user_input[CONF_BATTERY_DISCHARGE_W]):
        return {"base": "invalid_battery_thresholds"}
    return {}


def validate_forecast(
    hass: HomeAssistant,
    user_input: Mapping[str, Any],
    **_: Any,
) -> dict[str, str]:
    """Validate the EV-first inputs, which are either all set or all empty."""
    if errors := _validate_entities(hass, user_input, _FORECAST_OPTIONAL_DOMAINS, required=False):
        return errors
    if errors := _validate_power_units(hass, user_input, (CONF_SOLAR_POWER_ENTITY,)):
        return errors

    forecast_entity = user_input.get(CONF_FORECAST_REMAINING_ENTITY)
    if forecast_entity:
        forecast_state = hass.states.get(forecast_entity)
        if forecast_state is not None and forecast_state.attributes.get("unit_of_measurement") not in _ENERGY_UNITS:
            return {"base": "invalid_energy_unit"}

    if any(user_input.get(key) for key in _EV_FIRST_KEYS) and not all(user_input.get(key) for key in _EV_FIRST_KEYS):
        return {"base": "ev_first_incomplete"}
    return {}


def validate_offpeak(
    _hass: HomeAssistant,
    user_input: Mapping[str, Any],
    **_: Any,
) -> dict[str, str]:
    """Validate the off-peak windows."""
    return validate_windows(user_input)


def validate_solar(
    _hass: HomeAssistant,
    _user_input: Mapping[str, Any],
    **_: Any,
) -> dict[str, str]:
    """Accept the Solar timing page; every field is already range-checked by its selector."""
    return {}


PAGE_VALIDATORS: dict[str, PageValidator] = {
    "charger": validate_charger,
    "solar": validate_solar,
    "battery": validate_battery,
    "forecast": validate_forecast,
    "offpeak": validate_offpeak,
}
