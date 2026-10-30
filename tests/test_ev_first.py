"""Tests for forecast-based EV-first charging."""

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None
    return entity_id


def _set_sun(hass: HomeAssistant, hours: float) -> None:
    hass.states.async_set(
        "sun.sun",
        "above_horizon",
        {"next_setting": (dt_util.utcnow() + timedelta(hours=hours)).isoformat()},
    )


@pytest.fixture
async def ev_first_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up an entry with the EV-first inputs configured and a sunny forecast."""
    hass.states.async_set("sensor.forecast_remaining", "20", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.battery_level", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.solar_production", "500", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.battery_power", "-2000", {"unit_of_measurement": "W"})
    _set_sun(hass, 6)
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            CONF_FORECAST_REMAINING_ENTITY: "sensor.forecast_remaining",
            CONF_BATTERY_LEVEL_ENTITY: "sensor.battery_level",
            CONF_SOLAR_POWER_ENTITY: "sensor.solar_production",
            CONF_BATTERY_CAPACITY_KWH: 27,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _turn_on(hass: HomeAssistant, entry: MockConfigEntry, *keys: str) -> None:
    for key in keys:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": _entity_id(hass, entry, "switch", key)},
            blocking=True,
        )
    await hass.async_block_till_done()


async def test_ev_first_adds_battery_charge_power_to_the_solar_budget(
    hass: HomeAssistant,
    ev_first_entry: MockConfigEntry,
) -> None:
    """A covering forecast lets the EV use the power flowing into the battery."""
    await _turn_on(hass, ev_first_entry, "enabled", "solar_enabled", "ev_first_enabled")

    active = _entity_id(hass, ev_first_entry, "binary_sensor", "ev_first_active")
    budget = _entity_id(hass, ev_first_entry, "sensor", "available_solar_budget")
    assert hass.states.get(active).state == "on"
    assert float(hass.states.get(budget).state) == 2000

    hass.states.async_set("sensor.forecast_remaining", "5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()

    assert hass.states.get(active).state == "off"
    assert float(hass.states.get(budget).state) == 0


async def test_ev_first_switch_is_refused_without_forecast_inputs(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The switch cannot be turned on until the forecast inputs are configured."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": _entity_id(hass, init_integration, "switch", "ev_first_enabled")},
            blocking=True,
        )


async def test_house_power_is_production_plus_grid_and_battery_less_charger(
    hass: HomeAssistant,
    ev_first_entry: MockConfigEntry,
) -> None:
    """House use excludes the charger and counts battery discharge, not charging."""
    watts = {"unit_of_measurement": "W"}
    hass.states.async_set("sensor.solar_production", "3000", watts)
    hass.states.async_set("sensor.grid_power", "-500", watts)
    hass.states.async_set("sensor.charger_power", "1000", watts)
    hass.states.async_set("sensor.battery_power", "400", watts)
    await hass.async_block_till_done()
    coordinator = ev_first_entry.runtime_data.coordinator

    assert coordinator._house_power_w() == 1900  # noqa: SLF001

    hass.states.async_set("sensor.solar_production", "unavailable", watts)
    assert coordinator._house_power_w() is None  # noqa: SLF001
