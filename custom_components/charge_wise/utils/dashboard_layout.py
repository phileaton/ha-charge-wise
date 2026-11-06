"""Lay out the generated dashboard."""

from collections.abc import Mapping
from typing import Any

from custom_components.charge_wise.const import (
    BATTERY_SIGN_NEGATIVE,
    CONF_BATTERY_DISCHARGE_SIGN,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_EV_FIRST_RELEASE_MARGIN_PERCENT,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_MAXIMUM_CURRENT_A,
    CONF_OFFPEAK_WINDOWS,
    CONF_SOLAR_ENERGY_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    DEFAULT_BATTERY_DISCHARGE_SIGN,
    DEFAULT_EV_FIRST_RELEASE_MARGIN_PERCENT,
)

type Card = dict[str, Any]

_TREND_HOURS = 6
_AMBER = "#ffa000"
_GREEN = "#43a047"
_RED = "#e53935"


def _watts(entity_id: str) -> str:
    """Return a template expression giving the entity's reading in watts, whether it reports W or kW."""
    return f"(states('{entity_id}') | float(0) * (1000 if state_attr('{entity_id}', 'unit_of_measurement') == 'kW' else 1))"


def _tile(entity_id: str, name: str, color: str, *, trend: bool = True, columns: int = 6) -> Card:
    """Return a tile that shows the live value with a small trend graph beneath it."""
    card: Card = {
        "type": "tile",
        "entity": entity_id,
        "name": name,
        "color": color,
        "vertical": False,
        "grid_options": {"columns": columns},
    }
    if trend:
        card["features"] = [{"type": "trend-graph", "hours_to_show": _TREND_HOURS}]
        card["features_position"] = "bottom"
    return card


def _heading(title: str, icon: str, badges: list[Card] | None = None) -> Card:
    """Return a section heading, optionally carrying entity badges."""
    card: Card = {"type": "heading", "heading": title, "heading_style": "title", "icon": icon}
    if badges:
        card["badges"] = badges
    return card


def _power_value(entity_id: str, name: str, *, grid: bool = False) -> Card:
    """Return a compact power reading in kW with unavailable values kept explicit."""
    value = "{{ (power / 1000) | round(2) }} kW"
    if grid:
        value = (
            "{% if power > 50 %}Importing {{ (power / 1000) | round(2) }} kW"
            "{% elif power < -50 %}Exporting {{ (-power / 1000) | round(2) }} kW"
            "{% else %}Balanced{% endif %}"
        )
    return {
        "type": "markdown",
        "content": f"**{name}**\n\n"
        f"{{% if is_number(states('{entity_id}')) %}}"
        f"{{% set power = {_watts(entity_id)} %}}"
        f"{value}{{% else %}}Unavailable{{% endif %}}",
        "grid_options": {"columns": 6, "rows": 2},
    }


def _live_section(ids: Mapping[str, str], options: Mapping[str, Any]) -> list[Card]:
    """Return the section of live power tiles and the energy flow summary."""
    cards = [_heading("Live power", "mdi:flash")]
    if solar := options.get(CONF_SOLAR_POWER_ENTITY):
        cards.append(_tile(solar, "Solar", "amber"))
    if "house_load" in ids:
        cards.append(_tile(ids["house_load"], "Home", "blue"))
    if grid := options.get(CONF_GRID_POWER_ENTITY):
        cards.append(_tile(grid, "Grid", "red"))
    if battery := options.get(CONF_BATTERY_POWER_ENTITY):
        cards.append(_tile(battery, "Battery", "green"))
    if charger := options.get(CONF_CHARGER_POWER_ENTITY):
        cards.append(_tile(charger, "EV charger", "purple", columns=12))
    cards.append(_flow_summary(options))
    return cards


def _flow_summary(options: Mapping[str, Any]) -> Card:
    """Return a markdown card whose template states where the power is going right now."""
    lines: list[str] = []
    grid = options.get(CONF_GRID_POWER_ENTITY)
    battery = options.get(CONF_BATTERY_POWER_ENTITY)
    charger = options.get(CONF_CHARGER_POWER_ENTITY)

    if grid:
        lines.append(f"{{% set grid = {_watts(grid)} %}}")
        lines.append(
            "{% if grid > 50 %}⬇️ **Importing {{ (grid / 1000) | round(2) }} kW** from the grid"
            "{% elif grid < -50 %}⬆️ **Exporting {{ (-grid / 1000) | round(2) }} kW** to the grid"
            "{% else %}⚖️ **Grid is balanced**{% endif %}",
        )
    if battery:
        negative = options.get(CONF_BATTERY_DISCHARGE_SIGN, DEFAULT_BATTERY_DISCHARGE_SIGN) == BATTERY_SIGN_NEGATIVE
        sign = "-" if negative else ""
        lines.append(f"{{% set batt = {sign}{_watts(battery)} %}}")
        lines.append(
            "{% if batt > 50 %}🔋 **Battery discharging {{ (batt / 1000) | round(2) }} kW**"
            "{% elif batt < -50 %}🔌 **Battery charging {{ (-batt / 1000) | round(2) }} kW**"
            "{% else %}🔋 **Battery idle**{% endif %}",
        )
    if charger:
        lines.append(f"{{% set ev = {_watts(charger)} %}}")
        lines.append(
            "{% if ev > 50 %}🚗 **EV charging at {{ (ev / 1000) | round(2) }} kW**{% else %}🚗 **EV not charging**{% endif %}",
        )
    return {
        "type": "markdown",
        "title": "Right now",
        "content": "\n\n".join(lines),
        "grid_options": {"columns": 12},
    }


def _gauge_segments(*stops: tuple[float, str]) -> list[Card]:
    """Return gauge segments from (start, color) pairs."""
    return [{"from": start, "color": color} for start, color in stops]


def _battery_and_ev_section(
    ids: Mapping[str, str],
    options: Mapping[str, Any],
    budget_in_kw: bool,
) -> list[Card]:
    """Return charging status, its reason and compact battery and EV readings."""
    cards = [_heading("Charging status", "mdi:ev-station")]
    if "controller_status" in ids:
        cards.append(_tile(ids["controller_status"], "Status", "purple", trend=False))
    if "ev_first_active" in ids:
        cards.append(_tile(ids["ev_first_active"], "EV-first active", "purple", trend=False))
    if "decision_reason" in ids:
        cards.append(
            {
                "type": "markdown",
                "content": f"**Why**\n\n{{{{ state_translated('{ids['decision_reason']}') }}}}",
                "grid_options": {"columns": 12},
            }
        )
    if level := options.get(CONF_BATTERY_LEVEL_ENTITY):
        cards.append(
            {
                "type": "gauge",
                "entity": level,
                "name": "Home battery",
                "min": 0,
                "max": 100,
                "needle": True,
                "segments": _gauge_segments((0, _RED), (20, _AMBER), (50, _GREEN)),
                "grid_options": {"columns": 6, "rows": 3},
            },
        )
    if "requested_current" in ids:
        cards.append(
            {
                "type": "gauge",
                "entity": ids["requested_current"],
                "name": "Requested current",
                "min": 0,
                "max": float(options.get(CONF_MAXIMUM_CURRENT_A, 32)),
                "needle": True,
                "segments": _gauge_segments((0, "#9e9e9e"), (6, "#8e63c7")),
                "grid_options": {"columns": 6, "rows": 3},
            }
        )
    if "available_solar_budget" in ids:
        entity = ids["available_solar_budget"]
        default_unit = "kW" if budget_in_kw else "W"
        watts = (
            f"(states('{entity}') | float(0) * "
            f"(1000 if (state_attr('{entity}', 'unit_of_measurement') or '{default_unit}') == 'kW' else 1))"
        )
        cards.append(
            {
                "type": "markdown",
                "content": f"**Solar available for EV**\n\n"
                f"{{% if is_number(states('{entity}')) %}}"
                f"{{{{ ({watts} / 1000) | round(2) }}}} kW\n"
                "{% else %}Unavailable{% endif %}",
                "grid_options": {"columns": 6, "rows": 2},
            }
        )
    if charger := options.get(CONF_CHARGER_POWER_ENTITY):
        cards.append(_power_value(charger, "Actual charger power"))
    return cards


def _budget_section(ids: Mapping[str, str], options: Mapping[str, Any]) -> list[Card]:
    """Return how the EV budget is calculated: house use, battery need and forecast surplus."""
    cards = [_heading("EV budget", "mdi:calculator-variant")]
    tiles = (
        ("average_house_load", "House average", "blue"),
        ("battery_need", "Battery still needs", "green"),
        ("forecast_surplus", "Forecast surplus", "yellow"),
        ("forecast_accuracy", "Production vs forecast", "orange"),
    )
    for key, name, color in tiles:
        if key in ids:
            card = _tile(
                ids[key],
                name,
                color,
                trend=key in {"house_load", "forecast_surplus"},
                columns=12 if key == "forecast_accuracy" else 6,
            )
            if key == "average_house_load":
                card = _power_value(ids[key], name)
            if key == "forecast_accuracy":
                card["state_content"] = ["state", "actual_vs_forecast"]
            cards.append(card)
    if "battery_need" in ids and "forecast_surplus" in ids:
        cards.append(_budget_summary(ids, options))
    if "next_offpeak_window" in ids:
        window = ids["next_offpeak_window"]
        enabled = ids.get("offpeak_enabled")
        content = ""
        if enabled:
            content += f"{{% if is_state('{enabled}', 'off') %}}Off-peak charging is disabled.{{% else %}}"
        if not options.get(CONF_OFFPEAK_WINDOWS):
            content += "No off-peak schedule configured."
        else:
            content += (
                f"{{% set start = as_datetime(states('{window}'), none) %}}"
                "{% if start is not none %}{{ as_local(start).strftime('%a %H:%M') }}"
                "{% else %}Schedule unavailable{% endif %}"
            )
        if enabled:
            content += "{% endif %}"
        cards.append({"type": "markdown", "content": "**Off-peak** · " + content, "grid_options": {"columns": 12}})
    return cards


def _budget_summary(ids: Mapping[str, str], options: Mapping[str, Any]) -> Card:
    """Return a markdown card that says whether the forecast covers the battery and the EV may share it."""
    need = ids["battery_need"]
    surplus = ids["forecast_surplus"]
    active = ids.get("ev_first_active", "")
    enabled = ids.get("ev_first_enabled", "")
    margin = float(options.get(CONF_EV_FIRST_RELEASE_MARGIN_PERCENT, DEFAULT_EV_FIRST_RELEASE_MARGIN_PERCENT))
    content = (
        f"{{% set need = states('{need}') | float(none) %}}"
        f"{{% set spare = states('{surplus}') | float(none) %}}"
        "{% if need is none or spare is none %}🌙 **Forecast balance unavailable** (the sun is down or an input is missing)"
        "{% else %}"
        "{% set covered = [spare / need * 100, 100] | min if need > 0 else 100 %}"
        "**Forecast balance: {{ [covered, 0] | max | round(0) | int }}% covered**\n\n"
        f"{{% if is_state('{active}', 'on') %}}"
        "{% if need <= 0 %}Battery target reached; battery-first priority is off. Solar charging is available."
        "{% else %}EV-first sharing is active; forecast surplus exceeds the battery's remaining need.{% endif %}"
        f"{{% elif is_state('{enabled}', 'on') %}}"
        "Battery-first mode is active. EV-first sharing is off; the EV may charge from sustained grid-export surplus. "
        "EV-first sharing can resume when forecast surplus exceeds "
        f"{{{{ (need * (1 + {margin} / 100)) | round(2) }}}} kWh "
        f"(battery need plus the {margin:g}% restart margin)."
        "{% else %}EV-first sharing is disabled; ordinary solar charging applies.{% endif %}"
        "{% endif %}"
    )
    return {"type": "markdown", "content": content, "grid_options": {"columns": 12}}


def _solar_forecast_graph(forecast_entity: str, solar_entity: str, solar_power_scale_to_kw: float) -> Card:
    """Return the forecast-versus-actual solar power graph."""
    return {
        "type": "custom:apexcharts-card",
        "header": {"show": True, "title": "Solar power: forecast vs actual (kW)"},
        "graph_span": "24h",
        "section_mode": True,
        "span": {"start": "day"},
        "now": {"show": True, "label": "Now"},
        "series": [
            {
                "entity": forecast_entity,
                "name": "Forecast",
                "type": "area",
                "color": "#90a4ae",
                "show": {"legend_value": False},
                "data_generator": (
                    "return (entity.attributes.detailedForecast || [])"
                    ".map(point => [Date.parse(point.period_start), point.pv_estimate])"
                    ".filter(([timestamp, value]) => Number.isFinite(timestamp) && value != null && Number.isFinite(Number(value)))"
                    ".map(([timestamp, value]) => [timestamp, Number(value)]);"
                ),
            },
            {
                "entity": solar_entity,
                "name": "Actual",
                "type": "line",
                "color": _AMBER,
                "transform": f"return x * {solar_power_scale_to_kw:g};",
                "unit": "kW",
                "extend_to": "now",
                "group_by": {"duration": "30min", "func": "avg"},
            },
        ],
        "grid_options": {"columns": "full", "rows": 6},
    }


def _solar_section(
    ids: Mapping[str, str],
    options: Mapping[str, Any],
    solar_power_scale_to_kw: float | None,
) -> list[Card]:
    """Return solar forecast tiles and the history of the power flows."""
    cards = [_heading("Solar and history", "mdi:solar-power-variant")]
    if forecast := options.get(CONF_FORECAST_REMAINING_ENTITY):
        cards.append(_tile(forecast, "Remaining today", "orange", trend=False, columns=6))
    if forecast_today := options.get(CONF_FORECAST_TODAY_ENTITY):
        cards.append(_tile(forecast_today, "Today’s forecast", "orange", trend=False, columns=6))
        if solar := options.get(CONF_SOLAR_POWER_ENTITY):
            if solar_power_scale_to_kw is None:
                cards.append(
                    {
                        "type": "markdown",
                        "content": "The forecast comparison chart needs a solar power sensor with a unit of mW, W, or kW.",
                        "grid_options": {"columns": 12},
                    },
                )
            else:
                if solar_energy := options.get(CONF_SOLAR_ENERGY_ENTITY):
                    cards.append(
                        {
                            "type": "statistic",
                            "entity": solar_energy,
                            "name": "Produced today",
                            "stat_type": "change",
                            "period": {"calendar": {"period": "day"}},
                            "grid_options": {"columns": 6},
                        },
                    )
                cards.append(_solar_forecast_graph(forecast_today, solar, solar_power_scale_to_kw))
    power = [
        entity
        for entity in (
            options.get(CONF_SOLAR_POWER_ENTITY),
            ids.get("house_load"),
            options.get(CONF_GRID_POWER_ENTITY),
            options.get(CONF_BATTERY_POWER_ENTITY),
            options.get(CONF_CHARGER_POWER_ENTITY),
        )
        if entity
    ]
    if power:
        cards.append(
            {
                "type": "history-graph",
                "title": "Power flows, last 24 hours",
                "hours_to_show": 24,
                "entities": power,
                "grid_options": {"columns": "full"},
            },
        )
    return cards


def _controls_section(ids: Mapping[str, str], control_keys: tuple[str, ...]) -> list[Card]:
    """Return named controls with current settings shown only for active modes."""
    names = {
        "enabled": "Charging enabled",
        "solar_enabled": "Solar charging",
        "ev_first_enabled": "EV-first charging",
        "offpeak_enabled": "Off-peak charging",
        "manual_override": "Manual override",
        "manual_current": "Manual current",
        "offpeak_current": "Off-peak current",
    }
    modes = {"manual_current": "manual_override", "offpeak_current": "offpeak_enabled"}
    rows: list[Card] = []
    for key in control_keys:
        if key not in ids:
            continue
        row: Card = {"entity": ids[key], "name": names[key]}
        if key in modes and modes[key] in ids:
            row = {"type": "conditional", "conditions": [{"entity": ids[modes[key]], "state": "on"}], "row": row}
        rows.append(row)
    return [
        _heading("Controls", "mdi:tune-variant"),
        {"type": "entities", "show_header_toggle": False, "entities": rows, "grid_options": {"columns": 12}},
    ]


def build_view(
    title: str,
    ids: Mapping[str, str],
    options: Mapping[str, Any],
    control_keys: tuple[str, ...],
    *,
    budget_in_kw: bool = True,
    solar_power_scale_to_kw: float | None = None,
) -> Card:
    """Build the dashboard view from the entity IDs this entry registered and its configured source entities.

    Power summaries use the live sensor unit, including user-selected W or kW.
    """
    sections = [
        _battery_and_ev_section(ids, options, budget_in_kw),
        _live_section(ids, options),
        _controls_section(ids, control_keys) + _budget_section(ids, options),
        _solar_section(ids, options, solar_power_scale_to_kw),
    ]
    return {
        "type": "sections",
        "title": title,
        "path": "charge-wise",
        "icon": "mdi:ev-station",
        "max_columns": 3,
        "sections": [
            {"type": "grid", "cards": cards, "column_span": 3 if index == len(sections) - 1 else 1}
            for index, cards in enumerate(sections)
        ],
    }
