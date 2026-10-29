"""Tests for Charge Wise entities and state-driven updates."""

from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import (
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    DOMAIN,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    """Resolve an integration entity by its stable unique ID."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform,
        DOMAIN,
        f"{entry.entry_id}_{key}",
    )
    assert entity_id is not None
    return entity_id


def _set_power(hass: HomeAssistant, entity_id: str, value: float, unit: str = "W") -> None:
    """Set a test power sensor state."""
    hass.states.async_set(entity_id, str(value), {"unit_of_measurement": unit})


async def test_setup_exposes_the_charge_wise_control_surface(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The configured entry creates translated control and diagnostic entities."""
    select_entity = _entity_id(hass, init_integration, "select", "mode")
    number_entity = _entity_id(hass, init_integration, "number", "manual_current")
    status_entity = _entity_id(hass, init_integration, "sensor", "controller_status")
    solar_entity = _entity_id(hass, init_integration, "sensor", "available_solar_budget")
    current_entity = _entity_id(hass, init_integration, "sensor", "requested_current")
    reason_entity = _entity_id(hass, init_integration, "sensor", "decision_reason")
    battery_entity = _entity_id(hass, init_integration, "binary_sensor", "battery_protection")

    assert hass.states.get(select_entity).state == "off"
    assert float(hass.states.get(number_entity).state) == 6
    assert hass.states.get(status_entity).state == "off"
    assert hass.states.get(solar_entity).state == "unknown"
    assert float(hass.states.get(current_entity).state) == 0
    assert hass.states.get(reason_entity).state == "off"
    assert hass.states.get(battery_entity).state == "off"


async def test_solar_budget_uses_charger_power_and_signed_grid_power(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Solar budget is the charger draw less net grid import."""
    _set_power(hass, "sensor.grid_power", 0.5, "kW")
    _set_power(hass, "sensor.charger_power", 1.5, "kW")
    mode_entity = _entity_id(hass, init_integration, "select", "mode")

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": mode_entity, "option": "solar"},
        blocking=True,
    )
    await hass.async_block_till_done()

    solar_entity = _entity_id(hass, init_integration, "sensor", "available_solar_budget")
    status_entity = _entity_id(hass, init_integration, "sensor", "controller_status")
    assert float(hass.states.get(solar_entity).state) == 1000
    assert hass.states.get(status_entity).state == "waiting"


async def test_battery_protection_entity_is_omitted_without_a_battery_sensor(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The conditional binary sensor does not exist when protection is unconfigured."""
    options: dict[str, Any] = config_entry.options.copy()
    options.pop(CONF_BATTERY_POWER_ENTITY)
    options.update(
        {
            CONF_CHARGER_SWITCH_ENTITY: "switch.second_charger",
            CONF_CURRENT_TARGET_ENTITY: "number.second_current",
            CONF_HARDWARE_MAXIMUM_ENTITY: "number.second_maximum",
        },
    )
    hass.states.async_set("switch.second_charger", "off")
    hass.states.async_set(
        "number.second_current",
        "6",
        {"unit_of_measurement": UnitOfElectricCurrent.AMPERE},
    )
    hass.states.async_set(
        "number.second_maximum",
        "32",
        {"unit_of_measurement": UnitOfElectricCurrent.AMPERE},
    )
    hass.states.async_set("sensor.grid_power", "0", {"unit_of_measurement": UnitOfPower.WATT})
    hass.states.async_set("sensor.charger_power", "0", {"unit_of_measurement": UnitOfPower.WATT})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Second charger",
        data={},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert (
        er.async_get(hass).async_get_entity_id(
            "binary_sensor",
            DOMAIN,
            f"{entry.entry_id}_battery_protection",
        )
        is None
    )


async def test_battery_protection_entity_is_removed_when_the_battery_sensor_is_removed(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Dropping the battery sensor from the options removes its stale registry entry."""
    registry = er.async_get(hass)
    unique_id = f"{init_integration.entry_id}_battery_protection"
    assert registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id) is not None

    options = dict(init_integration.options)
    options.pop(CONF_BATTERY_POWER_ENTITY)
    hass.config_entries.async_update_entry(init_integration, options=options)
    await hass.async_block_till_done()

    assert registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id) is None
