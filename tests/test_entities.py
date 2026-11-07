"""Tests for Charge Wise entities and state-driven updates."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache

from custom_components.charge_wise.const import (
    CONF_BATTERY_POWER_ENTITY,
    CONF_CHARGER_SWITCH_ENTITY,
    CONF_CURRENT_TARGET_ENTITY,
    CONF_HARDWARE_MAXIMUM_ENTITY,
    DOMAIN,
)
from custom_components.charge_wise.diagnostics import async_get_config_entry_diagnostics
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
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
    switch_entities = [
        _entity_id(hass, init_integration, "switch", key) for key in ("enabled", "solar_enabled", "manual_override")
    ]
    mode = _entity_id(hass, init_integration, "select", "offpeak_mode")
    assert hass.states.get(mode).state == "off"
    assert hass.states.get(mode).attributes["options"] == ["off", "on", "on_once"]
    offpeak_number = _entity_id(hass, init_integration, "number", "offpeak_current")
    next_window = _entity_id(hass, init_integration, "sensor", "next_offpeak_window")
    offpeak_active = _entity_id(hass, init_integration, "binary_sensor", "offpeak_active")
    number_entity = _entity_id(hass, init_integration, "number", "manual_current")
    status_entity = _entity_id(hass, init_integration, "sensor", "controller_status")
    solar_entity = _entity_id(hass, init_integration, "sensor", "available_solar_budget")
    current_entity = _entity_id(hass, init_integration, "sensor", "requested_current")
    reason_entity = _entity_id(hass, init_integration, "sensor", "decision_reason")
    battery_entity = _entity_id(hass, init_integration, "binary_sensor", "battery_protection")

    assert all(hass.states.get(entity_id).state == "off" for entity_id in switch_entities)
    assert float(hass.states.get(offpeak_number).state) == 32
    assert hass.states.get(next_window).state == "unknown"
    assert hass.states.get(offpeak_active).state == "off"
    assert float(hass.states.get(number_entity).state) == 32
    assert hass.states.get(status_entity).state == "off"
    assert float(hass.states.get(solar_entity).state) == 0
    assert float(hass.states.get(current_entity).state) == 0
    assert hass.states.get(reason_entity).state == "off"
    assert hass.states.get(battery_entity).state == "off"


async def test_current_numbers_are_bounded_by_the_live_hardware_maximum(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """A lower hardware maximum lowers the selectable range of both current numbers."""
    hass.states.async_set("number.hardware_maximum", "16", {"unit_of_measurement": UnitOfElectricCurrent.AMPERE})
    await hass.async_block_till_done()

    for key in ("manual_current", "offpeak_current"):
        entity_id = _entity_id(hass, init_integration, "number", key)
        assert float(hass.states.get(entity_id).attributes["max"]) == 16
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": entity_id, "value": 20},
                blocking=True,
            )


async def test_solar_budget_uses_charger_power_and_signed_grid_power(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Solar budget is the charger draw less net grid import."""
    _set_power(hass, "sensor.grid_power", 0.5, "kW")
    _set_power(hass, "sensor.charger_power", 1.5, "kW")

    for key in ("enabled", "solar_enabled"):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": _entity_id(hass, init_integration, "switch", key)},
            blocking=True,
        )
    await hass.async_block_till_done()

    solar_entity = _entity_id(hass, init_integration, "sensor", "available_solar_budget")
    status_entity = _entity_id(hass, init_integration, "sensor", "controller_status")
    assert float(hass.states.get(solar_entity).state) == 1.0
    assert hass.states.get(status_entity).state == "waiting"


async def test_solar_budget_stays_available_when_charge_wise_is_disabled(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The live solar budget remains visible in the dashboard while control is disabled."""
    _set_power(hass, "sensor.grid_power", -1.25, "kW")
    _set_power(hass, "sensor.charger_power", 0)
    await hass.async_block_till_done()

    solar_entity = _entity_id(hass, init_integration, "sensor", "available_solar_budget")
    enabled_entity = _entity_id(hass, init_integration, "switch", "enabled")
    assert hass.states.get(enabled_entity).state == "off"
    assert float(hass.states.get(solar_entity).state) == 1.25


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


async def test_stale_mode_select_entity_is_removed_on_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The replaced mode select does not linger as an unavailable entity."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "select",
        DOMAIN,
        f"{config_entry.entry_id}_mode",
        config_entry=config_entry,
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_entity_id("select", DOMAIN, f"{config_entry.entry_id}_mode") is None


async def test_current_numbers_keep_their_prior_value_across_restarts(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """The charger maximum is only the first-install default; a restored value wins."""
    entity_ids = {
        key: _entity_id(hass, init_integration, "number", key) for key in ("manual_current", "offpeak_current")
    }
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    mock_restore_cache(
        hass,
        [State(entity_ids["manual_current"], "10"), State(entity_ids["offpeak_current"], "12")],
    )

    assert await hass.config_entries.async_setup(init_integration.entry_id)
    await hass.async_block_till_done()

    assert float(hass.states.get(entity_ids["manual_current"]).state) == 10
    assert float(hass.states.get(entity_ids["offpeak_current"]).state) == 12


@pytest.mark.parametrize(("profile", "raw", "expected"), [("ocpp", "Preparing", "on"), ("wallbox", "Locked", "off")])
async def test_charger_status_drives_connection_without_commands(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    profile: str,
    raw: str,
    expected: str,
) -> None:
    """Status updates work while control is off and power does not imply unplugging."""
    options = dict(config_entry.options)
    options.pop("ev_connected_entity")
    options.update(charger_status_entity="sensor.status", charger_status_profile=profile)
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options=options)
    hass.states.async_set("sensor.status", raw)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    connected = _entity_id(hass, config_entry, "binary_sensor", "vehicle_connected")
    charging = _entity_id(hass, config_entry, "binary_sensor", "vehicle_charging")
    session = _entity_id(hass, config_entry, "sensor", "charger_session")
    assert hass.states.get(connected).state == expected
    assert hass.states.get(charging).state == "off"
    assert hass.states.get(session).attributes["profile"] == profile
    hass.states.async_set("sensor.status", "Charging")
    await hass.async_block_till_done()
    assert hass.states.get(connected).state == "on"
    assert hass.states.get(charging).state == "off"
    _set_power(hass, "sensor.charger_power", 0.2, "kW")
    await hass.async_block_till_done()
    assert hass.states.get(charging).state == "on"
    _set_power(hass, "sensor.charger_power", 75)
    await hass.async_block_till_done()
    assert hass.states.get(charging).state == "on"
    hass.states.async_set("sensor.charger_power", "unavailable")
    hass.states.async_set("sensor.status", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(connected).state == "unknown"
    assert hass.states.get(charging).state == "unknown"
    assert hass.states.get(session).state == "unknown"


async def test_unified_status_replaces_legacy_connection(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The unified source ignores a stale legacy selection in an existing entry."""
    options = {**config_entry.options, "charger_status_entity": "sensor.status", "charger_status_profile": "wallbox"}
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options=options)
    hass.states.async_set("sensor.status", "Locked")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entity = _entity_id(hass, config_entry, "binary_sensor", "vehicle_connected")
    assert hass.states.get(entity).state == "off"
    hass.states.async_set("binary_sensor.ev_connected", "unavailable")
    hass.states.async_set("sensor.status", "Locked, car connected")
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "on"


@pytest.mark.parametrize("supplier", ["ocpp", "wallbox"])
async def test_automatic_profile_uses_entity_registry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    supplier: str,
) -> None:
    """Automatic profile follows the supplying integration rather than the entity name."""
    status = er.async_get(hass).async_get_or_create("sensor", supplier, "test-status")
    hass.states.async_set(status.entity_id, "Charging")
    config_entry.add_to_hass(hass)
    options = {**config_entry.options, "charger_status_entity": status.entity_id, "charger_status_profile": "auto"}
    options.pop("ev_connected_entity")
    hass.config_entries.async_update_entry(config_entry, options=options)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    session = _entity_id(hass, config_entry, "sensor", "charger_session")
    assert hass.states.get(session).state == "charging"
    assert hass.states.get(session).attributes["profile"] == supplier


async def test_legacy_ocpp_mapping_pauses_on_unknown_status(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Old string selections still detect OCPP and stop treating arbitrary strings as connected."""
    config_entry.add_to_hass(hass)
    options = {**config_entry.options, "ev_connected_entity": "sensor.legacy_status"}
    hass.config_entries.async_update_entry(config_entry, options=options)
    hass.states.async_set("sensor.legacy_status", "Preparing")
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    connection = _entity_id(hass, config_entry, "binary_sensor", "vehicle_connected")
    assert hass.states.get(connection).state == "on"
    await hass.services.async_call(
        "switch",
        "turn_on",
        {
            "entity_id": _entity_id(hass, config_entry, "switch", "enabled"),
        },
        blocking=True,
    )
    hass.states.async_set("sensor.legacy_status", "Locked")
    await hass.async_block_till_done()
    assert hass.states.get(connection).state == "unknown"
    reason = _entity_id(hass, config_entry, "sensor", "decision_reason")
    assert hass.states.get(reason).state == "ev_status_unavailable"


async def test_diagnostics_include_serializable_observations(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Diagnostics expose source evidence as a mapping that can be downloaded."""
    result = await async_get_config_entry_diagnostics(hass, init_integration)
    assert result["coordinator"]["data"]["vehicle_connected"] is True
    assert result["coordinator"]["data"]["charger_connection_source"] == "binary_sensor.ev_connected"


@pytest.mark.parametrize(("raw", "expected"), [("on", "on"), ("off", "off"), ("unavailable", "unknown")])
async def test_unified_binary_source_has_unknown_session(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    raw: str,
    expected: str,
) -> None:
    """Binary sources report only connection; profile selection cannot add session evidence."""
    config_entry.add_to_hass(hass)
    options = {
        **config_entry.options,
        "charger_status_entity": "binary_sensor.ev_connected",
        "charger_status_profile": "custom",
    }
    hass.config_entries.async_update_entry(config_entry, options=options)
    hass.states.async_set("binary_sensor.ev_connected", raw)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    connected = _entity_id(hass, config_entry, "binary_sensor", "vehicle_connected")
    session = _entity_id(hass, config_entry, "sensor", "charger_session")
    assert hass.states.get(connected).state == expected
    assert hass.states.get(session).state == "unknown"
    assert hass.states.get(session).attributes["profile"] == "binary"
