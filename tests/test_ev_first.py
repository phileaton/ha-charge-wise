"""Tests for forecast-based EV-first charging."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_LEVEL_ENTITY,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_SOLAR_ENERGY_ENTITY,
    CONF_SOLAR_POWER_ENTITY,
    DOMAIN,
)
from homeassistant.core import HomeAssistant, ServiceCall
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
    assert float(hass.states.get(budget).state) == 2.0

    hass.states.async_set("sensor.forecast_remaining", "5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()

    assert hass.states.get(active).state == "off"
    assert float(hass.states.get(budget).state) == 0


async def test_ev_first_forecast_shortfall_stops_solar_charging(
    hass: HomeAssistant,
    ev_first_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Solar-mode charging pauses when the forecast cannot cover the battery need."""
    watts = {"unit_of_measurement": "W"}
    hass.states.async_set("sensor.grid_power", "-7200", watts)
    await hass.async_block_till_done()
    await _turn_on(hass, ev_first_entry, "enabled", "ev_first_enabled", "solar_enabled")

    async def set_current(call: ServiceCall) -> None:
        hass.states.async_set(
            call.data["entity_id"],
            str(call.data["value"]),
            {"unit_of_measurement": "A"},
        )

    async def turn_on(call: ServiceCall) -> None:
        hass.states.async_set(call.data["entity_id"], "on")

    async def turn_off(call: ServiceCall) -> None:
        hass.states.async_set(call.data["entity_id"], "off")

    hass.services.async_register("number", "set_value", set_current)
    hass.services.async_register("switch", "turn_on", turn_on)
    hass.services.async_register("switch", "turn_off", turn_off)
    freezer.tick(31)
    await ev_first_entry.runtime_data.coordinator._async_evaluate()  # noqa: SLF001
    await hass.async_block_till_done()

    charger = hass.states.get("switch.charger_enable")
    assert charger is not None
    assert charger.state == "on"

    hass.states.async_set("sensor.forecast_remaining", "9.5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()

    active = hass.states.get(_entity_id(hass, ev_first_entry, "binary_sensor", "ev_first_active"))
    charger = hass.states.get("switch.charger_enable")
    assert active is not None
    assert active.state == "on"
    assert charger is not None
    assert charger.state == "on"

    hass.states.async_set("sensor.forecast_remaining", "5", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()

    reason = hass.states.get(_entity_id(hass, ev_first_entry, "sensor", "decision_reason"))
    charger = hass.states.get("switch.charger_enable")
    assert reason is not None
    assert reason.state == "ev_first_waiting"
    assert charger is not None
    assert charger.state == "off"


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


async def test_budget_sensors_publish_house_use_and_the_forecast_balance(
    hass: HomeAssistant,
    ev_first_entry: MockConfigEntry,
) -> None:
    """The dashboard's budget figures come from the same calculation the controller uses."""
    watts = {"unit_of_measurement": "W"}
    hass.states.async_set("sensor.solar_production", "3000", watts)
    hass.states.async_set("sensor.grid_power", "-500", watts)
    hass.states.async_set("sensor.charger_power", "1000", watts)
    hass.states.async_set("sensor.battery_power", "400", watts)
    await hass.async_block_till_done()

    house = hass.states.get(_entity_id(hass, ev_first_entry, "sensor", "house_load"))
    need = hass.states.get(_entity_id(hass, ev_first_entry, "sensor", "battery_need"))
    surplus = hass.states.get(_entity_id(hass, ev_first_entry, "sensor", "forecast_surplus"))
    assert float(house.state) == 1.9
    assert house.attributes["unit_of_measurement"] == "kW"
    assert float(need.state) == pytest.approx(10.8)
    assert float(surplus.state) < 20


async def test_ev_first_hold_state_is_restored_after_a_restart_on_the_same_day(
    hass: HomeAssistant,
    ev_first_entry: MockConfigEntry,
) -> None:
    """A restart keeps the release-margin hold."""
    coordinator = ev_first_entry.runtime_data.coordinator
    coordinator._ev_first_was_active = True  # noqa: SLF001
    saved = coordinator._ev_first_as_dict()  # noqa: SLF001
    coordinator._reset_ev_first()  # noqa: SLF001

    coordinator._restore_ev_first(saved)  # noqa: SLF001

    assert coordinator._ev_first_was_active  # noqa: SLF001

    coordinator._reset_ev_first()  # noqa: SLF001
    coordinator._restore_ev_first({**saved, "date": "2000-01-01"})  # noqa: SLF001

    assert not coordinator._ev_first_was_active  # noqa: SLF001


async def test_measured_accuracy_scales_the_forecast_surplus(
    hass: HomeAssistant,
    ev_first_entry: MockConfigEntry,
) -> None:
    """When the panels deliver half of the forecast so far, only half of what remains is counted."""
    coordinator = ev_first_entry.runtime_data.coordinator
    accuracy_id = _entity_id(hass, ev_first_entry, "sensor", "forecast_accuracy")
    assert hass.states.get(accuracy_id).state == "unknown"

    today = dt_util.now().date()
    coordinator.forecast_accuracy.restore(
        {
            "day": today.isoformat(),
            "baseline_forecast_kwh": 0.0,
            "latest_forecast_kwh": 10.0,
            "actual_kwh": 5.0,
        },
        today,
    )
    await coordinator._async_evaluate()  # noqa: SLF001
    await hass.async_block_till_done()

    assert float(hass.states.get(accuracy_id).state) == pytest.approx(50)
    assert hass.states.get(accuracy_id).attributes["actual_vs_forecast"] == "5.0 of 10.0 kWh"


async def test_energy_counter_drives_the_forecast_accuracy(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The configured energy counter's growth is compared with the forecast so far."""
    hass.states.async_set("sensor.forecast_remaining", "20", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.forecast_total", "20", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.solar_total", "100", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.battery_level", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.solar_production", "500", {"unit_of_measurement": "W"})
    _set_sun(hass, 6)
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            CONF_FORECAST_REMAINING_ENTITY: "sensor.forecast_remaining",
            CONF_FORECAST_TODAY_ENTITY: "sensor.forecast_total",
            CONF_SOLAR_ENERGY_ENTITY: "sensor.solar_total",
            CONF_BATTERY_LEVEL_ENTITY: "sensor.battery_level",
            CONF_SOLAR_POWER_ENTITY: "sensor.solar_production",
            CONF_BATTERY_CAPACITY_KWH: 27,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    accuracy_id = _entity_id(hass, config_entry, "sensor", "forecast_accuracy")

    hass.states.async_set("sensor.forecast_remaining", "16", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.solar_total", "103", {"unit_of_measurement": "kWh"})
    await hass.async_block_till_done()
    await config_entry.runtime_data.coordinator._async_evaluate()  # noqa: SLF001
    await hass.async_block_till_done()

    assert float(hass.states.get(accuracy_id).state) == pytest.approx(75)
