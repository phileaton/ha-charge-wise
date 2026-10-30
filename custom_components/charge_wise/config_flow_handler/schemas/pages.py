"""Selectors and defaults for each page of the Charge Wise setup and options flows."""

from collections.abc import Callable, Mapping
from typing import Any

import probatio

from custom_components.charge_wise.config_flow_handler.schemas.windows import add_window_fields
from custom_components.charge_wise.const import (
    BATTERY_SIGN_NEGATIVE,
    BATTERY_SIGN_POSITIVE,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CONFIRMATION_S,
    CONF_BATTERY_DISCHARGE_SIGN,
    CONF_BATTERY_DISCHARGE_W,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_RECOVERY_CONFIRMATION_S,
    CONF_BATTERY_RECOVERY_W,
    CONF_BATTERY_TARGET_PERCENT,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_COOLDOWN_S,
    CONF_CURRENT_DEADBAND_A,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_EV_CONNECTED_ENTITY,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TRUST_PERCENT,
    CONF_GRID_POWER_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    CONF_HOUSE_POWER_ENTITY,
    CONF_LOW_SOLAR_CONFIRMATION_S,
    CONF_MAXIMUM_CURRENT_A,
    CONF_MINIMUM_CURRENT_A,
    CONF_SOLAR_START_W,
    CONF_VOLTAGE_V,
    DEFAULT_BATTERY_CONFIRMATION_S,
    DEFAULT_BATTERY_DISCHARGE_SIGN,
    DEFAULT_BATTERY_DISCHARGE_W,
    DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S,
    DEFAULT_BATTERY_RECOVERY_W,
    DEFAULT_BATTERY_TARGET_PERCENT,
    DEFAULT_COOLDOWN_S,
    DEFAULT_CURRENT_DEADBAND_A,
    DEFAULT_FORECAST_TRUST_PERCENT,
    DEFAULT_LOW_SOLAR_CONFIRMATION_S,
    DEFAULT_MINIMUM_CURRENT_A,
    DEFAULT_SOLAR_START_W,
    DEFAULT_VOLTAGE_V,
)
from homeassistant.helpers import selector

_SENSOR_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_SWITCH_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))
_NUMBER_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="number"))
_BINARY_SENSOR_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor"))

type Schema = dict[probatio.Marker, selector.Selector]


def charger_schema(defaults: Mapping[str, Any]) -> probatio.Schema:
    """Build the page that selects the charger entities and its current limits."""
    schema: Schema = {
        probatio.Required(CONF_GRID_POWER_ENTITY): _SENSOR_SELECTOR,
        probatio.Required(CONF_CHARGER_POWER_ENTITY): _SENSOR_SELECTOR,
        probatio.Required(CONF_CHARGER_SWITCH_ENTITY): _SWITCH_SELECTOR,
        probatio.Required(CONF_CURRENT_TARGET_ENTITY): _NUMBER_SELECTOR,
        probatio.Optional(CONF_HARDWARE_MAXIMUM_ENTITY): _NUMBER_SELECTOR,
        probatio.Optional(CONF_EV_CONNECTED_ENTITY): _BINARY_SENSOR_SELECTOR,
    }
    _add_number_field(schema, defaults, CONF_MINIMUM_CURRENT_A, DEFAULT_MINIMUM_CURRENT_A, 1, 32, 1, "A")
    _add_number_field(schema, defaults, CONF_MAXIMUM_CURRENT_A, None, 1, 80, 1, "A")
    _add_number_field(schema, defaults, CONF_VOLTAGE_V, DEFAULT_VOLTAGE_V, 100, 300, 1, "V")
    return probatio.Schema(schema)


def solar_schema(defaults: Mapping[str, Any]) -> probatio.Schema:
    """Build the page with the Solar start and stop timing."""
    schema: Schema = {}
    _add_number_field(schema, defaults, CONF_SOLAR_START_W, DEFAULT_SOLAR_START_W, 100, 100_000, 100, "W")
    _add_number_field(
        schema,
        defaults,
        CONF_LOW_SOLAR_CONFIRMATION_S,
        DEFAULT_LOW_SOLAR_CONFIRMATION_S,
        1,
        600,
        1,
        "s",
    )
    _add_number_field(schema, defaults, CONF_COOLDOWN_S, DEFAULT_COOLDOWN_S, 0, 3600, 1, "s")
    _add_number_field(schema, defaults, CONF_CURRENT_DEADBAND_A, DEFAULT_CURRENT_DEADBAND_A, 0, 10, 0.5, "A")
    return probatio.Schema(schema)


def battery_schema(defaults: Mapping[str, Any]) -> probatio.Schema:
    """Build the page for battery discharge protection."""
    schema: Schema = {
        probatio.Optional(CONF_BATTERY_POWER_ENTITY): _SENSOR_SELECTOR,
        probatio.Required(
            CONF_BATTERY_DISCHARGE_SIGN,
            default=defaults.get(CONF_BATTERY_DISCHARGE_SIGN, DEFAULT_BATTERY_DISCHARGE_SIGN),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[BATTERY_SIGN_POSITIVE, BATTERY_SIGN_NEGATIVE],
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
    }
    _add_number_field(schema, defaults, CONF_BATTERY_DISCHARGE_W, DEFAULT_BATTERY_DISCHARGE_W, 1, 100_000, 1, "W")
    _add_number_field(schema, defaults, CONF_BATTERY_RECOVERY_W, DEFAULT_BATTERY_RECOVERY_W, 0, 100_000, 1, "W")
    _add_number_field(schema, defaults, CONF_BATTERY_CONFIRMATION_S, DEFAULT_BATTERY_CONFIRMATION_S, 1, 600, 1, "s")
    _add_number_field(
        schema,
        defaults,
        CONF_BATTERY_RECOVERY_CONFIRMATION_S,
        DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S,
        1,
        600,
        1,
        "s",
    )
    return probatio.Schema(schema)


def forecast_schema(defaults: Mapping[str, Any]) -> probatio.Schema:
    """Build the page for forecast-based EV-first charging."""
    schema: Schema = {
        probatio.Optional(CONF_FORECAST_REMAINING_ENTITY): _SENSOR_SELECTOR,
        probatio.Optional(CONF_BATTERY_LEVEL_ENTITY): _SENSOR_SELECTOR,
        probatio.Optional(CONF_HOUSE_POWER_ENTITY): _SENSOR_SELECTOR,
        probatio.Optional(CONF_BATTERY_CAPACITY_KWH): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=500,
                step=0.1,
                unit_of_measurement="kWh",
                mode=selector.NumberSelectorMode.BOX,
            ),
        ),
    }
    _add_number_field(schema, defaults, CONF_BATTERY_TARGET_PERCENT, DEFAULT_BATTERY_TARGET_PERCENT, 1, 100, 1, "%")
    _add_number_field(schema, defaults, CONF_FORECAST_TRUST_PERCENT, DEFAULT_FORECAST_TRUST_PERCENT, 1, 100, 1, "%")
    return probatio.Schema(schema)


def offpeak_schema(_defaults: Mapping[str, Any]) -> probatio.Schema:
    """Build the page with the off-peak windows."""
    schema: Schema = {}
    add_window_fields(schema)
    return probatio.Schema(schema)


PAGES = ("charger", "solar", "battery", "forecast", "offpeak")

PAGE_SCHEMAS: dict[str, Callable[[Mapping[str, Any]], probatio.Schema]] = {
    "charger": charger_schema,
    "solar": solar_schema,
    "battery": battery_schema,
    "forecast": forecast_schema,
    "offpeak": offpeak_schema,
}


def _add_number_field(
    schema: Schema,
    defaults: Mapping[str, Any],
    key: str,
    default: float | None,
    minimum: float,
    maximum: float,
    step: float,
    unit: str,
) -> None:
    """Add a numeric selector, leaving the explicit hardware maximum unset for new entries."""
    marker = (
        probatio.Required(key, default=defaults[key])
        if key in defaults
        else probatio.Required(key, default=default)
        if default is not None
        else probatio.Required(key)
    )
    schema[marker] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        ),
    )


__all__ = ["PAGES", "PAGE_SCHEMAS"]
