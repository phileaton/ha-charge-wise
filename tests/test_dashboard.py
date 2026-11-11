"""Tests for the generated Charge Wise dashboard."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import (
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_CREATE_DASHBOARD,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_SOLAR_ENERGY_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
)
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.lovelace import LovelaceData
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

URL_PATH = "test-charger"


async def _setup(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    *,
    create: bool,
    options: dict[str, Any] | None = None,
) -> None:
    hass.data[LOVELACE_DATA] = LovelaceData(
        resource_mode="storage",
        dashboards={},
        resources=None,  # type: ignore[arg-type]
        yaml_dashboards={},
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, **(options or {}), CONF_CREATE_DASHBOARD: create},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_dashboard_is_created_with_the_entry_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The opted-in dashboard lists this entry's real entities."""
    hass.states.async_set(
        "sensor.solcast_forecast_today",
        "52.83",
        {
            "unit_of_measurement": "kWh",
            "detailedForecast": [{"period_start": "2026-11-04T10:00:00+00:00", "pv_estimate": 2.5}],
        },
    )
    hass.states.async_set(
        "sensor.solcast_forecast_remaining",
        "49.79",
        {"unit_of_measurement": "kWh"},
    )
    hass.states.async_set("sensor.solar_power", "3200", {"unit_of_measurement": "W"})
    await _setup(
        hass,
        config_entry,
        create=True,
        options={
            CONF_BATTERY_LEVEL_ENTITY: "sensor.home_battery_level",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.solcast_forecast_remaining",
            CONF_FORECAST_TODAY_ENTITY: "sensor.solcast_forecast_today",
            CONF_SOLAR_POWER_ENTITY: "sensor.solar_power",
            CONF_SOLAR_ENERGY_ENTITY: "sensor.solar_energy_lifetime",
        },
    )

    dashboard = hass.data[LOVELACE_DATA].dashboards[URL_PATH]
    config = await dashboard.async_load(False)
    view = config["views"][0]
    cards = [card for section in view["sections"] for card in section["cards"]]
    entities = {card["entity"] for card in cards if "entity" in card}
    assert URL_PATH in hass.data[DATA_PANELS]
    assert view["type"] == "sections"
    assert [section["cards"][0]["heading"] for section in view["sections"]] == [
        "Charging status",
        "Live power",
        "Controls",
        "Solar and history",
    ]
    assert view["sections"][-1]["column_span"] == 3
    assert {"sensor.grid_power", "sensor.charger_power", "sensor.battery_power"} <= entities
    grid_tile = next(card for card in cards if card.get("name") == "Grid")
    assert grid_tile["type"] == "tile"
    assert grid_tile["features"] == [{"type": "trend-graph", "hours_to_show": 6}]
    assert "sensor.test_charger_house_consumption" in entities
    assert any("sensor.test_charger_available_solar_budget" in card.get("content", "") for card in cards)
    assert "sensor.test_charger_forecast_accuracy" in entities
    assert sum(card.get("entity") == "sensor.test_charger_forecast_accuracy" for card in cards) == 1
    accuracy_tile = next(card for card in cards if card.get("entity") == "sensor.test_charger_forecast_accuracy")
    assert accuracy_tile["state_content"] == ["state", "actual_vs_forecast"]
    assert any(card["type"] == "gauge" for card in cards)
    assert any(card["type"] == "history-graph" for card in cards)
    chart = next(card for card in cards if card["type"] == "custom:apexcharts-card")
    help_card = cards[cards.index(chart) - 1]
    assert help_card["type"] == "markdown"
    assert help_card["title"] == "Graph troubleshooting"
    assert "ApexCharts Card 2.2.0 or newer" in help_card["content"]
    assert "Configuration error" in help_card["content"]
    assert "HACS" in help_card["content"]
    assert "Resources" in help_card["content"]
    assert "refresh your browser" in help_card["content"]
    assert chart["header"]["title"] == "Solar power: forecast vs actual (kW)"
    forecast_series, actual_series = chart["series"]
    assert "detailedForecast" in forecast_series["data_generator"]
    assert "pv_estimate" in forecast_series["data_generator"]
    assert actual_series["entity"] == "sensor.solar_power"
    assert actual_series["transform"] == "return x * 0.001;"
    assert actual_series["extend_to"] == "now"
    assert forecast_series["show"] == {"legend_value": False}
    forecast_tiles = [
        card
        for card in cards
        if card.get("entity") in {"sensor.solcast_forecast_today", "sensor.solcast_forecast_remaining"}
    ]
    assert {card["name"] for card in forecast_tiles} == {
        "Remaining today",
        "Today’s forecast",
    }
    assert all("features" not in card for card in forecast_tiles)
    production = next(card for card in cards if card.get("entity") == "sensor.solar_energy_lifetime")
    assert production["type"] == "statistic"
    assert production["stat_type"] == "change"
    assert production["period"] == {"calendar": {"period": "day"}}
    controls = next(card for card in cards if card["type"] == "entities")
    assert len(controls["entities"]) == 7
    assert any(row.get("entity", "").startswith("switch.test_charger") for row in controls["entities"])
    conditional = [row for row in controls["entities"] if row.get("type") == "conditional"]
    assert {row["row"]["name"] for row in conditional} == {"Manual current", "Off-peak current"}
    assert any(row.get("entity", "").startswith("select.test_charger") for row in controls["entities"])
    conditions = {row["row"]["name"]: row["conditions"][0] for row in conditional}
    assert conditions["Manual current"]["state"] == "on"
    assert conditions["Off-peak current"]["state_not"] == "off"
    assert conditions["Off-peak current"]["entity"].startswith("select.")
    assert sum(card["type"] == "gauge" for card in cards) == 2
    assert chart["grid_options"] == {"columns": "full", "rows": 6}
    assert chart["section_mode"] is True
    current = next(card for card in cards if card.get("name") == "Actual charging power")
    assert current["type"] == "gauge"
    assert current["max"] == 7680
    battery = next(card for card in cards if card.get("name") == "Home battery")
    assert current["grid_options"] == battery["grid_options"]
    assert any("state_translated" in card.get("content", "") for card in cards)
    assert any(card.get("heading") == "EV budget" for card in view["sections"][2]["cards"])


async def test_dashboard_is_not_created_unless_requested(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Entries without the option get no dashboard."""
    await _setup(hass, config_entry, create=False)

    assert URL_PATH not in hass.data[LOVELACE_DATA].dashboards


async def test_dashboard_is_removed_when_turned_off_or_the_entry_is_deleted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Untick the option or delete the entry and the dashboard goes away."""
    await _setup(hass, config_entry, create=True)
    assert URL_PATH in hass.data[LOVELACE_DATA].dashboards

    hass.config_entries.async_update_entry(config_entry, options={**config_entry.options, CONF_CREATE_DASHBOARD: False})
    await hass.async_block_till_done()
    assert URL_PATH not in hass.data[LOVELACE_DATA].dashboards

    hass.config_entries.async_update_entry(config_entry, options={**config_entry.options, CONF_CREATE_DASHBOARD: True})
    await hass.async_block_till_done()
    assert URL_PATH in hass.data[LOVELACE_DATA].dashboards

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert URL_PATH not in hass.data[LOVELACE_DATA].dashboards


async def test_dashboard_templates_render_the_live_flow(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The markdown cards are valid templates that describe the current power flow."""
    await _setup(hass, config_entry, create=True)
    watts = {"unit_of_measurement": "W"}
    hass.states.async_set("sensor.grid_power", "-1500", watts)
    hass.states.async_set("sensor.charger_power", "2000", watts)
    hass.states.async_set("sensor.battery_power", "-500", watts)
    await hass.async_block_till_done()

    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    cards = [card for section in config["views"][0]["sections"] for card in section["cards"]]
    markdown = [card for card in cards if card["type"] == "markdown"]
    rendered = [Template(card["content"], hass).async_render() for card in markdown]

    assert any("Exporting 1.5 kW" in text and "Battery charging 0.5 kW" in text for text in rendered)
    assert any("EV charging at 2.0 kW" in text for text in rendered)
    assert not any("Solar covers" in text for text in rendered)
    assert any("Off-peak charging is disabled" in text for text in rendered)
    budget = next(card for card in markdown if "Solar available for EV" in card["content"])
    hass.states.async_set("sensor.test_charger_available_solar_budget", "7950", watts)
    assert "7.95 kW" in Template(budget["content"], hass).async_render()
    hass.states.async_set("sensor.test_charger_available_solar_budget", "7.95", {"unit_of_measurement": "kW"})
    assert "7.95 kW" in Template(budget["content"], hass).async_render()
    hass.states.async_set("sensor.test_charger_available_solar_budget", "unavailable")
    assert "Unavailable" in Template(budget["content"], hass).async_render()
    grid = next(card for card in markdown if card.get("title") == "Right now")
    hass.states.async_set("sensor.grid_power", "-0.0", {"unit_of_measurement": "kW"})
    assert "Grid is balanced" in Template(grid["content"], hass).async_render()
    average = next(card for card in markdown if "**House average**" in card["content"])
    hass.states.async_set("sensor.test_charger_average_house_consumption", "2075", watts)
    assert "2.08 kW" in Template(average["content"], hass).async_render()
    assert not any(card["type"] == "custom:apexcharts-card" for card in cards)
    assert not any(card.get("title") == "Graph troubleshooting" for card in cards)


async def test_forecast_message_follows_sharing_permission(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The forecast message reports actual permission and the restart surplus threshold."""
    await _setup(hass, config_entry, create=True)
    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    cards = [card for section in config["views"][0]["sections"] for card in section["cards"]]
    balance = next(card for card in cards if "Forecast balance:" in card.get("content", ""))
    hass.states.async_set("sensor.test_charger_battery_energy_needed", "15")
    hass.states.async_set("sensor.test_charger_forecast_surplus_after_house_use", "20")
    hass.states.async_set("select.test_charger_ev_first_charging", "on")
    hass.states.async_set("binary_sensor.test_charger_ev_first_active", "on")
    rendered = Template(balance["content"], hass).async_render()
    assert "sharing is active" in rendered
    assert "Battery-first:" not in rendered
    hass.states.async_set("binary_sensor.test_charger_ev_first_active", "off")
    rendered = Template(balance["content"], hass).async_render()
    assert "Battery-first mode is active" in rendered
    assert "grid-export surplus" in rendered
    assert "18.75 kWh" in rendered
    assert "25% restart margin" in rendered
    hass.states.async_set("select.test_charger_ev_first_charging", "on_once")
    assert "Battery-first mode is active" in Template(balance["content"], hass).async_render()
    controls = next(card for card in cards if card.get("type") == "entities")
    assert any(row.get("entity") == "select.test_charger_ev_first_charging" for row in controls["entities"])
    hass.states.async_set("select.test_charger_ev_first_charging", "off")
    assert "EV-first sharing is disabled" in Template(balance["content"], hass).async_render()


async def test_actual_current_gauge_keeps_requested_limit_separate(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """A connected car refusing to draw power shows zero actual current alongside its allowed limit."""
    hass.states.async_set("sensor.measured_current", "0", {"unit_of_measurement": "A"})
    await _setup(hass, config_entry, create=True, options={"charger_current_entity": "sensor.measured_current"})
    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    cards = [card for section in config["views"][0]["sections"] for card in section["cards"]]
    gauge = next(card for card in cards if card.get("name") == "Actual current")
    assert gauge["entity"] == "sensor.measured_current"
    assert gauge["max"] == 32
    warning = next(card for card in cards if card.get("type") == "conditional" and "card" in card)
    assert warning["conditions"] == [
        {"entity": "binary_sensor.test_charger_ev_drawing_less_than_offered", "state": "on"}
    ]
    assert "EV drawing less than offered" in warning["card"]["content"]
    assert not any(card.get("name") == "Requested current" for card in cards)
    summary = next(card for card in cards if "Requested limit:" in card.get("content", ""))
    coordinator = config_entry.runtime_data.coordinator
    await coordinator.async_set_manual_current(32)
    await hass.async_block_till_done()
    rendered = Template(summary["content"], hass).async_render()
    assert "Connected, not drawing power" in rendered
    assert "Requested limit:" in rendered
    assert hass.states.get(gauge["entity"]).state == "0"
    hass.states.async_set("sensor.measured_current", "unavailable")
    hass.states.async_set("sensor.charger_power", "unavailable", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert "Vehicle activity unknown" in Template(summary["content"], hass).async_render()


async def test_power_gauge_uses_native_kw_scale(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Without measured amps the dashboard shows watts, scaled to the sensor's actual unit."""
    hass.states.async_set("sensor.charger_power", "0", {"unit_of_measurement": "kW"})
    await _setup(hass, config_entry, create=True)
    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    cards = [card for section in config["views"][0]["sections"] for card in section["cards"]]
    gauge = next(card for card in cards if card.get("name") == "Actual charging power")
    assert gauge["entity"] == "sensor.charger_power"
    assert gauge["max"] == 7.68


async def test_multiple_vehicle_cards_render_read_only_status(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Render configured readings live, hiding absent fields and preserving unavailable values."""
    hass.states.async_set("sensor.ev_battery", "64.4", {"unit_of_measurement": "%"})
    hass.states.async_set("number.ev_target", "80", {"unit_of_measurement": "%"})
    hass.states.async_set("binary_sensor.ev_plugged", "on")
    hass.states.async_set("binary_sensor.ev_charging", "off")
    hass.states.async_set("sensor.ev_power", "4000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.ev_range", "269", {"unit_of_measurement": "mi"})
    hass.states.async_set("sensor.ev_time", "90", {"unit_of_measurement": "min"})
    vehicles = [
        {
            "id": "rivian",
            "name": "Rivian",
            "battery_entity": "sensor.ev_battery",
            "charge_target_entity": "number.ev_target",
            "connected_entity": "binary_sensor.ev_plugged",
            "charging_entity": "binary_sensor.ev_charging",
            "charging_power_entity": "sensor.ev_power",
            "range_entity": "sensor.ev_range",
            "time_remaining_entity": "sensor.ev_time",
        },
        {"id": "tesla", "name": "Tesla", "battery_entity": "sensor.ev_battery"},
    ]
    await _setup(hass, config_entry, create=True, options={"vehicles": vehicles})
    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    section = next(s for s in config["views"][0]["sections"] if s["cards"][0].get("heading") == "Vehicles")
    rivian, tesla = section["cards"][1:]
    assert rivian["cards"][0]["name"] == "Rivian"
    assert rivian["cards"][0]["entity"] == "sensor.ev_battery"
    assert tesla["cards"] == [{**rivian["cards"][0], "name": "Tesla"}]
    content = rivian["cards"][1]["content"]
    rendered = Template(content, hass).async_render()
    for expected in ("80.0 %", "Plugged in:** Yes", "Charging:** No", "4000.0 W", "269.0 mi", "90.0 min"):
        assert expected in rendered
    hass.states.async_set("sensor.ev_power", "unavailable", {"unit_of_measurement": "W"})
    assert "Charging power:** Unavailable" in Template(content, hass).async_render()
    hass.states.async_set("binary_sensor.ev_charging", "unknown")
    assert "Charging:** Unavailable" in Template(content, hass).async_render()
    assert hass.states.get("number.ev_target").state == "80"


async def test_restart_cooldown_card_uses_live_relative_deadline(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Only show the cooldown row while waiting, using frontend-managed relative time."""
    await _setup(hass, config_entry, create=True)
    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    status = config["views"][0]["sections"][0]["cards"]
    card = next(card for card in status if card.get("type") == "conditional" and card["card"].get("type") == "entities")
    assert card["conditions"] == [{"entity": "sensor.test_charger_decision_reason", "state": "cooldown"}]
    assert card["card"]["entities"] == [
        {"entity": "sensor.test_charger_restart_cooldown_ends", "time_format": "relative"}
    ]


@pytest.mark.parametrize(
    ("changes", "vehicle_changes", "expected"),
    [
        ({}, {}, "Estimated time to target:** 4 h 0 min"),
        ({"sensor.ev_power": ("10000", "W")}, {}, "Estimated time to target:** 4 h 0 min"),
        ({"sensor.ev_power": ("9.99", "kW")}, {}, "Estimated time to target:** 4 h 1 min"),
        ({"number.ev_target": ("80", "kWh")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_battery": ("40", "kWh")}, {}, "Time to finish:** Unavailable"),
        ({}, {"charging_entity": None, "connected_entity": None}, "Estimated time to target:** 4 h 0 min"),
        ({}, {"charge_target_entity": None}, "Estimated time to target:** 6 h 0 min"),
        ({"sensor.ev_time": ("90", "min")}, {"time_remaining_entity": "sensor.ev_time"}, "Time to finish:** 90.0 min"),
        (
            {"sensor.ev_time": ("unavailable", "min")},
            {"time_remaining_entity": "sensor.ev_time"},
            "Estimated time to target:** 4 h 0 min",
        ),
        (
            {"sensor.ev_time": ("-1", "min")},
            {"time_remaining_entity": "sensor.ev_time"},
            "Estimated time to target:** 4 h 0 min",
        ),
        ({"sensor.ev_power": ("0", "kW")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_power": ("-1", "kW")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_power": ("unavailable", "kW")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_power": ("inf", "kW")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_power": ("10", "mph")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_battery": ("unknown", "%")}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_battery": ("101", "%")}, {}, "Time to finish:** Unavailable"),
        ({"number.ev_target": ("unavailable", "%")}, {}, "Time to finish:** Unavailable"),
        ({"binary_sensor.ev_charging": ("off", None)}, {}, "Time to finish:** Unavailable"),
        ({"binary_sensor.ev_charging": ("unknown", None)}, {}, "Time to finish:** Unavailable"),
        ({"binary_sensor.ev_plugged": ("off", None)}, {}, "Time to finish:** Unavailable"),
        ({"sensor.ev_battery": ("80", "%")}, {}, "Estimated time to target:** 0 h 0 min"),
    ],
)
async def test_vehicle_charge_time_estimate(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    changes: dict[str, tuple[str, str | None]],
    vehicle_changes: dict[str, Any],
    expected: str,
) -> None:
    """Estimate only from valid current readings, prefer native time, and honor paused states."""
    readings = {
        "sensor.ev_battery": ("40", "%"),
        "number.ev_target": ("80", "%"),
        "sensor.ev_power": ("10", "kW"),
        "binary_sensor.ev_charging": ("on", None),
        "binary_sensor.ev_plugged": ("on", None),
        **changes,
    }
    for entity_id, (value, unit) in readings.items():
        hass.states.async_set(entity_id, value, {"unit_of_measurement": unit} if unit else {})
    vehicle = {
        "id": "tesla",
        "name": "Tesla",
        "battery_entity": "sensor.ev_battery",
        "battery_capacity_kwh": 100,
        "charge_target_entity": "number.ev_target",
        "charging_power_entity": "sensor.ev_power",
        "charging_entity": "binary_sensor.ev_charging",
        "connected_entity": "binary_sensor.ev_plugged",
        **vehicle_changes,
    }
    vehicle = {key: value for key, value in vehicle.items() if value is not None}
    await _setup(hass, config_entry, create=True, options={"vehicles": [vehicle]})
    config = await hass.data[LOVELACE_DATA].dashboards[URL_PATH].async_load(False)
    section = next(s for s in config["views"][0]["sections"] if s["cards"][0].get("heading") == "Vehicles")
    content = section["cards"][1]["cards"][1]["content"]
    rendered = Template(content, hass).async_render()
    assert expected in rendered
    assert rendered.count("time to target") + rendered.count("Time to finish") == 1
    if "Estimated time" in expected:
        assert "at the current rate" in rendered
