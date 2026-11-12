"""Native dashboard cards for the configured vehicles."""

from collections.abc import Mapping
from typing import Any

from custom_components.charge_wise.const import CONF_VEHICLES

_FIELDS = (
    "charge_target_entity",
    "connected_entity",
    "charging_entity",
    "charging_power_entity",
    "range_entity",
)


def _time_remaining(vehicle: Mapping[str, Any], labels: Mapping[str, str]) -> str | None:
    """Prefer the vehicle duration, otherwise estimate at the current charging power."""
    native = vehicle.get("time_remaining_entity")
    capacity = vehicle.get("battery_capacity_kwh")
    power = vehicle.get("charging_power_entity")
    if not native and capacity is None:
        return None
    unavailable = f"**{labels['time_remaining_entity']}:** {labels['unavailable']}"
    estimate = unavailable
    if capacity is not None and power:
        battery = vehicle["battery_entity"]
        target = vehicle.get("charge_target_entity")
        target_value = f"states('{target}') | float(none)" if target else "100"
        conditions = [
            "soc is not none",
            "target is not none",
            "0 <= soc <= 100",
            "0 <= target <= 100",
            "power is not none",
            "power > 0",
            "unit in ['W', 'kW']",
        ]
        conditions.extend(
            f"is_state('{source}', 'on')"
            for key in ("charging_entity", "connected_entity")
            if (source := vehicle.get(key))
        )
        conditions.append(f"is_number(states('{power}'))")
        conditions.append(f"state_attr('{battery}', 'unit_of_measurement') == '%'")
        if target:
            conditions.append(f"state_attr('{target}', 'unit_of_measurement') == '%'")
        estimate = (
            f"{{% set soc = states('{battery}') | float(none) %}}"
            f"{{% set target = {target_value} %}}"
            f"{{% set power = states('{power}') | float(none) %}}"
            f"{{% set unit = state_attr('{power}', 'unit_of_measurement') %}}"
            f"{{% if {' and '.join(conditions)} %}}"
            "{% set kw = power / 1000 if unit == 'W' else power %}"
            f"{{% set minutes = (({capacity!r} * ([target - soc, 0] | max) / 100 / kw) * 60) | round(0, 'ceil') | int %}}"
            f"**{labels['estimated_time_remaining']}:** "
            f"{{{{ minutes // 60 }}}} {labels['hours_unit']} {{{{ minutes % 60 }}}} {labels['minutes_unit']}"
            f" — {labels['at_current_rate']}"
            f"{{% else %}}{unavailable}{{% endif %}}"
        )
    if native:
        return (
            f"{{% set native = states('{native}') | float(none) %}}"
            f"{{% set native_unit = state_attr('{native}', 'unit_of_measurement') %}}"
            f"{{% if is_number(states('{native}')) and native >= 0 and native_unit in ['s', 'min', 'h'] %}}"
            f"**{labels['time_remaining_entity']}:** {{{{ native | round(1) }}}} {{{{ native_unit }}}}"
            f"{{% else %}}{estimate}{{% endif %}}"
        )
    return estimate


def vehicle_cards(options: Mapping[str, Any], labels: Mapping[str, str]) -> list[dict[str, Any]]:
    """Build battery gauges, status readings and supported charge-target controls."""
    cards: list[dict[str, Any]] = []
    unavailable = labels["unavailable"]
    yes = labels["yes"]
    no = labels["no"]
    for vehicle in options.get(CONF_VEHICLES, []):
        readings = []
        for key in _FIELDS:
            label = labels[key]
            if not (entity_id := vehicle.get(key)):
                continue
            if key in ("connected_entity", "charging_entity"):
                value = (
                    f"{{% if is_state('{entity_id}', 'on') %}}{yes}"
                    f"{{% elif is_state('{entity_id}', 'off') %}}{no}"
                    f"{{% else %}}{unavailable}{{% endif %}}"
                )
            else:
                value = (
                    f"{{% if is_number(states('{entity_id}')) %}}"
                    f"{{{{ states('{entity_id}') | float | round(1) }}}} "
                    f"{{{{ state_attr('{entity_id}', 'unit_of_measurement') or '' }}}}"
                    f"{{% else %}}{unavailable}{{% endif %}}"
                )
            readings.append(f"**{label}:** {value}")
        if time_remaining := _time_remaining(vehicle, labels):
            readings.append(time_remaining)
        contents: list[dict[str, Any]] = [
            {
                "type": "gauge",
                "entity": vehicle["battery_entity"],
                "name": vehicle["name"],
                "min": 0,
                "max": 100,
                "needle": True,
                "severity": {"red": 0, "yellow": 20, "green": 50},
            }
        ]
        if readings:
            contents.append({"type": "markdown", "content": "\n\n".join(readings)})
        if (target := vehicle.get("charge_target_entity", "")).startswith("number."):
            contents.append(
                {
                    "type": "tile",
                    "entity": target,
                    "name": labels["charge_target_entity"],
                    "features": [{"type": "numeric-input", "style": "buttons"}],
                }
            )
        cards.append({"type": "vertical-stack", "cards": contents, "grid_options": {"columns": 12}})
    if cards:
        cards.insert(
            0, {"type": "heading", "heading": labels["vehicles"], "heading_style": "title", "icon": "mdi:car-multiple"}
        )
    return cards
