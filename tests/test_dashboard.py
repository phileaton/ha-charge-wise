"""Tests for the generated Charge Wise dashboard."""

from typing import Any

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
    assert {"sensor.charger_power", "sensor.battery_power"} <= entities
    assert any("sensor.grid_power" in card.get("content", "") for card in cards)
    assert "sensor.test_charger_house_consumption" in entities
    assert any("sensor.test_charger_available_solar_budget" in card.get("content", "") for card in cards)
    assert "sensor.test_charger_forecast_accuracy" in entities
    assert sum(card.get("entity") == "sensor.test_charger_forecast_accuracy" for card in cards) == 1
    accuracy_tile = next(card for card in cards if card.get("entity") == "sensor.test_charger_forecast_accuracy")
    assert accuracy_tile["state_content"] == ["state", "actual_vs_forecast"]
    assert any(card["type"] == "gauge" for card in cards)
    assert any(card["type"] == "history-graph" for card in cards)
    chart = next(card for card in cards if card["type"] == "custom:apexcharts-card")
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
    assert all(row["conditions"][0]["state"] == "on" for row in conditional)
    assert sum(card["type"] == "gauge" for card in cards) == 2
    assert chart["grid_options"] == {"columns": "full", "rows": 6}
    assert chart["section_mode"] is True
    current = next(card for card in cards if card.get("name") == "Requested current")
    assert current["type"] == "gauge"
    assert current["max"] == 32
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
    grid = next(card for card in markdown if "**Grid**" in card["content"])
    hass.states.async_set("sensor.grid_power", "-0.0", {"unit_of_measurement": "kW"})
    assert "Balanced" in Template(grid["content"], hass).async_render()
    hass.states.async_set("sensor.grid_power", "unavailable")
    assert "Unavailable" in Template(grid["content"], hass).async_render()
    average = next(card for card in markdown if "**House average**" in card["content"])
    hass.states.async_set("sensor.test_charger_average_house_consumption", "2075", watts)
    assert "2.08 kW" in Template(average["content"], hass).async_render()
    assert not any(card["type"] == "custom:apexcharts-card" for card in cards)
