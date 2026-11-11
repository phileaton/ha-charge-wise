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
    "time_remaining_entity",
)


def vehicle_cards(options: Mapping[str, Any], labels: Mapping[str, str]) -> list[dict[str, Any]]:
    """Build one battery gauge and read-only status card per configured vehicle."""
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
        cards.append({"type": "vertical-stack", "cards": contents, "grid_options": {"columns": 12}})
    if cards:
        cards.insert(
            0, {"type": "heading", "heading": labels["vehicles"], "heading_style": "title", "icon": "mdi:car-multiple"}
        )
    return cards
