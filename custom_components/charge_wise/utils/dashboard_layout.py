"""Lay out the generated dashboard from core cards only, so it needs no frontend add-ons."""

from collections.abc import Mapping
from typing import Any

from custom_components.charge_wise.const import (
    BATTERY_SIGN_NEGATIVE,
    CONF_BATTERY_DISCHARGE_SIGN,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_MAXIMUM_CURRENT_A,
    CONF_SOLAR_POWER_ENTITY,
    CONF_SOLAR_START_W,
    CONF_VOLTAGE_V,
    DEFAULT_BATTERY_DISCHARGE_SIGN,
    DEFAULT_SOLAR_START_W,
    DEFAULT_VOLTAGE_V,
)

type Card = dict[str, Any]

_TREND_HOURS = 6
_GREY = "#9e9e9e"
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


def _badge(entity_id: str) -> Card:
    """Return a heading badge that shows an entity's state."""
    return {"type": "entity", "entity": entity_id, "show_state": True, "show_icon": True}


def _live_section(ids: Mapping[str, str], options: Mapping[str, Any]) -> list[Card]:
    """Return the section of live power tiles and the energy flow summary."""
    badges = [_badge(ids[key]) for key in ("controller_status", "ev_first_active") if key in ids]
    cards = [_heading("Live power", "mdi:flash", badges)]
    if solar := options.get(CONF_SOLAR_POWER_ENTITY):
        cards.append(_tile(solar, "Solar", "yellow"))
    if "house_load" in ids:
        cards.append(_tile(ids["house_load"], "Home", "blue"))
    if grid := options.get(CONF_GRID_POWER_ENTITY):
        cards.append(_tile(grid, "Grid (+ import / - export)", "red"))
    if battery := options.get(CONF_BATTERY_POWER_ENTITY):
        cards.append(_tile(battery, "Battery", "green"))
    if charger := options.get(CONF_CHARGER_POWER_ENTITY):
        cards.append(_tile(charger, "EV charger", "purple", columns=12))
    cards.append(_flow_summary(options))
    return cards


def _flow_summary(options: Mapping[str, Any]) -> Card:
    """Return a markdown card whose template states where the power is going right now."""
    lines: list[str] = []
    solar = options.get(CONF_SOLAR_POWER_ENTITY)
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
    if solar and charger:
        lines.append(f"{{% set sun = {_watts(solar)} %}}")
        lines.append(
            "{% set share = ([sun / ev * 100, 100] | min) if ev > 50 else 0 %}"
            "{% set filled = (share / 10) | round(0) | int %}"
            "{% if ev > 50 %}☀️ Solar covers `{{ '█' * filled }}{{ '░' * (10 - filled) }}` "
            "**{{ share | round(0) | int }}%** of the EV{% endif %}",
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
    budget_divisor: int,
) -> list[Card]:
    """Return the gauges for battery level, the solar budget and the requested charge current."""
    maximum_a = float(options.get(CONF_MAXIMUM_CURRENT_A, 32))
    voltage_v = float(options.get(CONF_VOLTAGE_V, DEFAULT_VOLTAGE_V))
    start_w = float(options.get(CONF_SOLAR_START_W, DEFAULT_SOLAR_START_W))
    cards = [_heading("Battery and EV", "mdi:ev-station")]
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
    if "available_solar_budget" in ids:
        cards.append(
            {
                "type": "gauge",
                "entity": ids["available_solar_budget"],
                "name": "Solar budget for the EV",
                "min": 0,
                "max": round(maximum_a * voltage_v / budget_divisor, 1),
                "needle": True,
                "segments": _gauge_segments(
                    (0, _GREY),
                    (start_w / budget_divisor, _AMBER),
                    (start_w * 2 / budget_divisor, _GREEN),
                ),
                "grid_options": {"columns": 6, "rows": 3},
            },
        )
    if "requested_current" in ids:
        cards.append(
            {
                "type": "gauge",
                "entity": ids["requested_current"],
                "name": "Charge current requested",
                "min": 0,
                "max": maximum_a,
                "needle": True,
                "segments": _gauge_segments((0, _GREY), (6, _GREEN)),
                "grid_options": {"columns": 12, "rows": 3},
            },
        )
    for key, name in (("controller_status", "Controller"), ("decision_reason", "Why")):
        if key in ids:
            cards.append(
                {
                    "type": "tile",
                    "entity": ids[key],
                    "name": name,
                    "color": "purple",
                    "grid_options": {"columns": 12},
                },
            )
    return cards


def _budget_section(ids: Mapping[str, str], options: Mapping[str, Any]) -> list[Card]:
    """Return how the EV budget is calculated: house use, battery need and forecast surplus."""
    cards = [_heading("EV budget", "mdi:calculator-variant")]
    tiles = (
        ("house_load", "House now", "blue"),
        ("average_house_load", "House average", "blue"),
        ("battery_need", "Battery still needs", "green"),
        ("forecast_surplus", "Forecast surplus", "yellow"),
    )
    for key, name, color in tiles:
        if key in ids:
            cards.append(_tile(ids[key], name, color, trend=key in {"house_load", "forecast_surplus"}))
    if "battery_need" in ids and "forecast_surplus" in ids:
        cards.append(_budget_summary(ids))
    if "next_offpeak_window" in ids:
        cards.append(
            {
                "type": "tile",
                "entity": ids["next_offpeak_window"],
                "name": "Next off-peak window",
                "color": "teal",
                "grid_options": {"columns": 12},
            },
        )
    return cards


def _budget_summary(ids: Mapping[str, str]) -> Card:
    """Return a markdown card that says whether the forecast covers the battery and the EV may share it."""
    need = ids["battery_need"]
    surplus = ids["forecast_surplus"]
    content = (
        f"{{% set need = states('{need}') | float(none) %}}"
        f"{{% set spare = states('{surplus}') | float(none) %}}"
        "{% if need is none or spare is none %}🌙 **Forecast balance unavailable** (the sun is down or an input is missing)"
        "{% else %}"
        "{% set covered = [spare / need * 100, 100] | min if need > 0 else 100 %}"
        "{% set filled = (covered / 10) | round(0) | int %}"
        "`{{ '█' * filled }}{{ '░' * (10 - filled) }}` "
        "**{{ [covered, 0] | max | round(0) | int }}%** of the battery's need is covered by the forecast\n\n"
        "{% if spare >= need %}✅ The forecast covers the battery, so the EV may share its charging power"
        "{% else %}⏳ The battery comes first until the forecast catches up{% endif %}"
        "{% endif %}"
    )
    return {"type": "markdown", "title": "Forecast balance", "content": content, "grid_options": {"columns": 12}}


def _solar_section(ids: Mapping[str, str], options: Mapping[str, Any]) -> list[Card]:
    """Return solar forecast tiles and a day-long history of the power flows."""
    cards = [_heading("Solar and history", "mdi:solar-power-variant")]
    if forecast := options.get(CONF_FORECAST_REMAINING_ENTITY):
        cards.append(_tile(forecast, "Forecast remaining today", "orange", columns=12))
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
                "grid_options": {"columns": 12},
            },
        )
    return cards


def _controls_section(ids: Mapping[str, str], control_keys: tuple[str, ...], title: str) -> list[Card]:
    """Return the section holding the user's switches and numbers."""
    return [
        _heading("Controls", "mdi:tune-variant"),
        {
            "type": "entities",
            "title": f"{title} controls",
            "show_header_toggle": False,
            "entities": [ids[key] for key in control_keys if key in ids],
            "grid_options": {"columns": 12},
        },
    ]


def build_view(
    title: str,
    ids: Mapping[str, str],
    options: Mapping[str, Any],
    control_keys: tuple[str, ...],
    *,
    budget_in_kw: bool = True,
) -> Card:
    """Build the dashboard view from the entity IDs this entry registered and its configured source entities.

    The solar budget gauge needs its scale in the unit the sensor reports, which the user can change.
    """
    sections = [
        _live_section(ids, options),
        _battery_and_ev_section(ids, options, 1000 if budget_in_kw else 1),
        _budget_section(ids, options),
        _solar_section(ids, options),
        _controls_section(ids, control_keys, title),
    ]
    return {
        "type": "sections",
        "title": title,
        "path": "charge-wise",
        "icon": "mdi:ev-station",
        "max_columns": 4,
        "sections": [{"type": "grid", "cards": cards} for cards in sections],
    }
