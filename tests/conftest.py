"""Shared fixtures for Charge Wise tests."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import (
    BATTERY_SIGN_POSITIVE,
    CONF_BATTERY_CONFIRMATION_S,
    CONF_BATTERY_DISCHARGE_SIGN,
    CONF_BATTERY_DISCHARGE_W,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_RECOVERY_CONFIRMATION_S,
    CONF_BATTERY_RECOVERY_W,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_COOLDOWN_S,
    CONF_CURRENT_DEADBAND_A,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_EV_CONNECTED_ENTITY,
    CONF_GRID_POWER_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    CONF_LOW_SOLAR_CONFIRMATION_S,
    CONF_MAXIMUM_CURRENT_A,
    CONF_MINIMUM_CURRENT_A,
    CONF_SOLAR_START_W,
    CONF_VOLTAGE_V,
    DEFAULT_BATTERY_CONFIRMATION_S,
    DEFAULT_BATTERY_DISCHARGE_W,
    DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S,
    DEFAULT_BATTERY_RECOVERY_W,
    DEFAULT_COOLDOWN_S,
    DEFAULT_CURRENT_DEADBAND_A,
    DEFAULT_LOW_SOLAR_CONFIRMATION_S,
    DEFAULT_MINIMUM_CURRENT_A,
    DEFAULT_SOLAR_START_W,
    DEFAULT_VOLTAGE_V,
    DOMAIN,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS: dict[str, Any] = {
    CONF_GRID_POWER_ENTITY: "sensor.grid_power",
    CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
    CONF_CHARGER_SWITCH_ENTITY: "switch.charger_enable",
    CONF_CURRENT_TARGET_ENTITY: "number.current_limit",
    CONF_HARDWARE_MAXIMUM_ENTITY: "number.hardware_maximum",
    CONF_BATTERY_POWER_ENTITY: "sensor.battery_power",
    CONF_BATTERY_DISCHARGE_SIGN: BATTERY_SIGN_POSITIVE,
    CONF_EV_CONNECTED_ENTITY: "binary_sensor.ev_connected",
    CONF_MINIMUM_CURRENT_A: DEFAULT_MINIMUM_CURRENT_A,
    CONF_MAXIMUM_CURRENT_A: 32,
    CONF_VOLTAGE_V: DEFAULT_VOLTAGE_V,
    CONF_SOLAR_START_W: DEFAULT_SOLAR_START_W,
    CONF_LOW_SOLAR_CONFIRMATION_S: DEFAULT_LOW_SOLAR_CONFIRMATION_S,
    CONF_COOLDOWN_S: DEFAULT_COOLDOWN_S,
    CONF_BATTERY_DISCHARGE_W: DEFAULT_BATTERY_DISCHARGE_W,
    CONF_BATTERY_RECOVERY_W: DEFAULT_BATTERY_RECOVERY_W,
    CONF_BATTERY_CONFIRMATION_S: DEFAULT_BATTERY_CONFIRMATION_S,
    CONF_BATTERY_RECOVERY_CONFIRMATION_S: DEFAULT_BATTERY_RECOVERY_CONFIRMATION_S,
    CONF_CURRENT_DEADBAND_A: DEFAULT_CURRENT_DEADBAND_A,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load Charge Wise as a custom integration in every test."""


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create the selected source entities and a configured Charge Wise entry."""
    hass.states.async_set(
        "sensor.grid_power",
        "0",
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set(
        "sensor.charger_power",
        "0",
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set(
        "sensor.battery_power",
        "0",
        {"unit_of_measurement": UnitOfPower.WATT},
    )
    hass.states.async_set("binary_sensor.ev_connected", "on")
    hass.states.async_set(
        "switch.charger_enable",
        "off",
        {"friendly_name": "Test charger"},
    )
    hass.states.async_set(
        "number.current_limit",
        "6",
        {
            "unit_of_measurement": UnitOfElectricCurrent.AMPERE,
            "min": 6,
            "max": 32,
            "step": 1,
        },
    )
    hass.states.async_set(
        "number.hardware_maximum",
        "32",
        {
            "unit_of_measurement": UnitOfElectricCurrent.AMPERE,
            "min": 6,
            "max": 32,
            "step": 1,
        },
    )
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test charger",
        data={},
        options=DEFAULT_OPTIONS.copy(),
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Set up Charge Wise and return the loaded config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
