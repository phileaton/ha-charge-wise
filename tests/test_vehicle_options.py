"""Vehicle settings through the Home Assistant options-flow interface."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import InvalidData
from homeassistant.helpers import entity_registry as er


async def _vehicles(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "vehicles"})


async def _step(hass: HomeAssistant, result: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    return await hass.config_entries.options.async_configure(result["flow_id"], values)


async def test_add_edit_remove_multiple_vehicles(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Save any number of vehicles while retaining unrelated charger options."""
    original = dict(config_entry.options)
    hass.states.async_set("sensor.ev_battery", "64.4", {"unit_of_measurement": "%"})
    hass.states.async_set("number.ev_target", "80", {"unit_of_measurement": "%"})
    result = await _vehicles(hass, config_entry)
    for index in range(4):
        result = await _step(hass, result, {"next_step_id": "vehicle_add"})
        result = await _step(
            hass,
            result,
            {"name": f"EV {index}", "battery_entity": "sensor.ev_battery", "charge_target_entity": "number.ev_target"},
        )
        assert result["step_id"] == "vehicles"
    assert "vehicles" not in config_entry.options
    result = await _step(hass, result, {"next_step_id": "vehicle_edit"})
    choices = next(iter(result["data_schema"].schema.values())).config["options"]
    first = choices[0]["value"]
    second = choices[1]["value"]
    result = await _step(hass, result, {"vehicle_id": first})
    markers = {str(marker): marker for marker in result["data_schema"].schema}
    assert markers["name"].description["suggested_value"] == "EV 0"
    result = await _step(hass, result, {"name": "Rivian", "battery_entity": "sensor.ev_battery"})
    result = await _step(hass, result, {"next_step_id": "vehicle_remove"})
    result = await _step(hass, result, {"vehicle_id": second})
    result = await _step(hass, result, {"next_step_id": "vehicle_save"})
    assert result["type"] == "create_entry"
    saved = result["data"]
    assert {key: saved[key] for key in original} == original
    assert [v["name"] for v in saved["vehicles"]] == ["Rivian", "EV 2", "EV 3"]
    assert saved["vehicles"][0]["id"] == first
    assert "charge_target_entity" not in saved["vehicles"][0]


@pytest.mark.parametrize(
    ("values", "field", "error"),
    [
        ({"name": "  "}, "name", "vehicle_name_required"),
        ({"battery_entity": "sensor.charger_power"}, "battery_entity", "vehicle_invalid_unit"),
        ({"range_entity": "sensor.missing"}, "range_entity", "vehicle_invalid_entity"),
        ({"time_remaining_entity": "sensor.ev_battery"}, "time_remaining_entity", "vehicle_invalid_unit"),
    ],
)
async def test_vehicle_validation_recovers(
    hass: HomeAssistant, config_entry: MockConfigEntry, values: dict[str, Any], field: str, error: str
) -> None:
    """Invalid mappings stay on the form and can be corrected without losing the flow."""
    hass.states.async_set("sensor.ev_battery", "80", {"unit_of_measurement": "%"})
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_add"})
    result = await _step(hass, result, {"name": "Tesla", "battery_entity": "sensor.ev_battery", **values})
    assert result["errors"][field] == error
    result = await _step(hass, result, {"name": "Tesla", "battery_entity": "sensor.ev_battery"})
    assert result["step_id"] == "vehicles"


async def test_abandon_vehicle_edits_preserves_saved_options(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Closing an unfinished flow never writes the staged list."""
    original = dict(config_entry.options)
    hass.states.async_set("sensor.ev_battery", "80", {"unit_of_measurement": "%"})
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_add"})
    result = await _step(hass, result, {"name": "Tesla", "battery_entity": "sensor.ev_battery"})
    hass.config_entries.options.async_abort(result["flow_id"])
    assert dict(config_entry.options) == original


async def test_registered_unavailable_battery_can_be_selected(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An asleep vehicle with a registered percentage sensor remains configurable."""
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "test", "ev_battery", suggested_object_id="sleeping_ev", unit_of_measurement="%"
    )
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_add"})
    result = await _step(hass, result, {"name": "Tesla", "battery_entity": entry.entity_id})
    assert result["step_id"] == "vehicles"


async def test_wrong_entity_domain_is_rejected_by_selector(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The binary selector rejects numeric sources before the flow accepts them."""
    hass.states.async_set("sensor.ev_battery", "80", {"unit_of_measurement": "%"})
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_add"})
    with pytest.raises(InvalidData):
        await _step(
            hass,
            result,
            {"name": "Tesla", "battery_entity": "sensor.ev_battery", "connected_entity": "sensor.ev_battery"},
        )
    result = await _step(hass, result, {"name": "Tesla", "battery_entity": "sensor.ev_battery"})
    assert result["step_id"] == "vehicles"


async def test_remove_last_vehicle(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Removing every vehicle saves an empty list and retains charger settings."""
    config_entry.add_to_hass(hass)
    original = dict(config_entry.options)
    hass.config_entries.async_update_entry(
        config_entry,
        options={**original, "vehicles": [{"id": "tesla", "name": "Tesla", "battery_entity": "sensor.battery"}]},
    )
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_remove"})
    result = await _step(hass, result, {"vehicle_id": "tesla"})
    assert "vehicle_edit" not in result["menu_options"]
    result = await _step(hass, result, {"next_step_id": "vehicle_save"})
    assert result["data"] == {**original, "vehicles": []}


async def test_vehicle_capacity_requires_power_and_can_be_edited_and_cleared(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Capacity is optional, requires a power source, and survives editing until explicitly cleared."""
    hass.states.async_set("sensor.ev_battery", "40", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.ev_power", "10", {"unit_of_measurement": "kW"})
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_add"})
    values = {"name": "Tesla", "battery_entity": "sensor.ev_battery", "battery_capacity_kwh": 100}
    result = await _step(hass, result, values)
    assert result["errors"] == {"charging_power_entity": "vehicle_estimate_power_required"}
    values["charging_power_entity"] = "sensor.ev_power"
    result = await _step(hass, result, values)
    result = await _step(hass, result, {"next_step_id": "vehicle_edit"})
    vehicle_id = next(iter(result["data_schema"].schema.values())).config["options"][0]["value"]
    result = await _step(hass, result, {"vehicle_id": vehicle_id})
    fields = {str(marker): marker for marker in result["data_schema"].schema}
    assert fields["battery_capacity_kwh"].description["suggested_value"] == 100
    result = await _step(hass, result, {**values, "battery_capacity_kwh": 95.5})
    result = await _step(hass, result, {"next_step_id": "vehicle_save"})
    assert result["data"]["vehicles"][0]["battery_capacity_kwh"] == 95.5
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await _step(hass, result, {"next_step_id": "vehicles"})
    result = await _step(hass, result, {"next_step_id": "vehicle_edit"})
    result = await _step(hass, result, {"vehicle_id": vehicle_id})
    result = await _step(hass, result, {"name": "Tesla", "battery_entity": "sensor.ev_battery"})
    result = await _step(hass, result, {"next_step_id": "vehicle_save"})
    assert "battery_capacity_kwh" not in result["data"]["vehicles"][0]


@pytest.mark.parametrize("capacity", [0, -1, 1001])
async def test_vehicle_capacity_selector_rejects_out_of_range(
    hass: HomeAssistant, config_entry: MockConfigEntry, capacity: float
) -> None:
    """Invalid capacities are rejected before they can be saved."""
    hass.states.async_set("sensor.ev_battery", "40", {"unit_of_measurement": "%"})
    result = await _vehicles(hass, config_entry)
    result = await _step(hass, result, {"next_step_id": "vehicle_add"})
    with pytest.raises(InvalidData):
        await _step(
            hass, result, {"name": "Tesla", "battery_entity": "sensor.ev_battery", "battery_capacity_kwh": capacity}
        )
