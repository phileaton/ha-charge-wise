"""Selectors for dashboard vehicle readings."""

from typing import Any

import probatio

from homeassistant.helpers import selector

VEHICLE_FIELDS: dict[str, tuple[list[str], tuple[str, ...]]] = {
    "battery_entity": (["sensor"], ("%",)),
    "charge_target_entity": (["sensor", "number"], ("%",)),
    "connected_entity": (["binary_sensor"], ()),
    "charging_entity": (["binary_sensor"], ()),
    "charging_power_entity": (["sensor"], ("W", "kW")),
    "range_entity": (["sensor"], ("km", "mi", "m")),
    "time_remaining_entity": (["sensor"], ("s", "min", "h")),
}


def vehicle_schema() -> probatio.Schema:
    """Require a display name and battery reading, with optional additional readings."""
    fields: dict[Any, Any] = {probatio.Required("name"): selector.TextSelector()}
    for key, (domains, _) in VEHICLE_FIELDS.items():
        marker = probatio.Required(key) if key == "battery_entity" else probatio.Optional(key)
        fields[marker] = selector.EntitySelector(selector.EntitySelectorConfig(domain=domains))
    fields[probatio.Optional("battery_capacity_kwh")] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.1, max=1000, step=0.1, unit_of_measurement="kWh", mode=selector.NumberSelectorMode.BOX
        )
    )
    return probatio.Schema(fields)
