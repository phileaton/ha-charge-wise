"""Tests for the multi-page, entity-based Charge Wise config and options flows."""

from typing import Any

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import CONF_OFFPEAK_WINDOWS, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

_CHARGER_KEYS = {
    "grid_power_entity",
    "charger_power_entity",
    "charger_switch_entity",
    "current_target_entity",
    "hardware_maximum_entity",
    "ev_connected_entity",
    "minimum_current_a",
    "maximum_current_a",
    "voltage_v",
}
_SOLAR_KEYS = {"solar_start_w", "low_solar_confirmation_s", "cooldown_s", "current_deadband_a"}
_BATTERY_KEYS = {
    "battery_power_entity",
    "battery_discharge_sign",
    "battery_discharge_w",
    "battery_recovery_w",
    "battery_confirmation_s",
    "battery_recovery_confirmation_s",
}
_PAGES = ("charger", "solar", "battery", "forecast", "offpeak")


def _pages(options: dict[str, Any], **extra: Any) -> list[dict[str, Any]]:
    """Split flat options into the input of each page."""
    options = {k: v for k, v in options.items() if k != CONF_OFFPEAK_WINDOWS}
    forecast = {k: v for k, v in options.items() if k not in _CHARGER_KEYS | _SOLAR_KEYS | _BATTERY_KEYS}
    return [
        {k: v for k, v in options.items() if k in _CHARGER_KEYS},
        {k: v for k, v in options.items() if k in _SOLAR_KEYS},
        {k: v for k, v in options.items() if k in _BATTERY_KEYS},
        forecast,
        dict(extra),
    ]


async def _walk_setup(hass: HomeAssistant, pages: list[dict[str, Any]]) -> FlowResult:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    for page_input in pages:
        assert result["type"] == "form"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=page_input)
    return result


async def _walk_options(hass: HomeAssistant, entry: MockConfigEntry, pages: list[dict[str, Any]]) -> FlowResult:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    for page_input in pages:
        assert result["type"] == "form"
        result = await hass.config_entries.options.async_configure(result["flow_id"], user_input=page_input)
    return result


async def test_config_flow_shows_one_page_per_topic(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The setup flow walks the pages in order and only creates the entry after the last."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    step_ids = [result["step_id"]]
    for page_input in _pages(config_entry.options)[:-1]:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=page_input)
        step_ids.append(result["step_id"])

    assert step_ids == ["user", "solar", "battery", "forecast", "offpeak"]
    assert result["type"] == "form"


async def test_config_flow_stores_entity_mappings_in_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """A valid setup creates an entry without credentials or network access."""
    result = await _walk_setup(hass, _pages(config_entry.options))

    assert result["type"] == "create_entry"
    assert result["data"] == {}
    assert result["options"]["grid_power_entity"] == "sensor.grid_power"
    assert result["options"]["battery_discharge_w"] == config_entry.options["battery_discharge_w"]
    assert "username" not in result["options"]
    assert "password" not in result["options"]


async def test_config_flow_rejects_reused_charger_controls(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Charger switches and current targets cannot be claimed by two entries."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=_pages(config_entry.options)[0],
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "already_configured"}


async def test_config_flow_rejects_invalid_battery_thresholds_on_the_battery_page(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """A page error keeps the user on that page."""
    pages = _pages(config_entry.options)
    pages[2] |= {"battery_recovery_w": 900, "battery_discharge_w": 100}
    result = await _walk_setup(hass, pages[:3])

    assert result["step_id"] == "battery"
    assert result["errors"] == {"base": "invalid_battery_thresholds"}


async def test_options_flow_rejects_partial_ev_first_inputs(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The forecast page needs all four inputs or none."""
    config_entry.add_to_hass(hass)
    hass.states.async_set("sensor.forecast", "10", {"unit_of_measurement": "kWh"})
    pages = _pages(config_entry.options)
    pages[3] = {
        "forecast_remaining_entity": "sensor.forecast",
        "battery_target_percent": 90,
        "forecast_trust_percent": 80,
    }
    result = await _walk_options(hass, config_entry, pages[:4])

    assert result["step_id"] == "forecast"
    assert result["errors"] == {"base": "ev_first_incomplete"}


async def test_options_flow_rejects_a_non_energy_forecast_sensor(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The forecast sensor must report an energy unit."""
    config_entry.add_to_hass(hass)
    hass.states.async_set("sensor.level", "50", {"unit_of_measurement": "%"})
    pages = _pages(config_entry.options)
    pages[3] = {
        "forecast_remaining_entity": "sensor.grid_power",
        "battery_level_entity": "sensor.level",
        "house_power_entity": "sensor.grid_power",
        "battery_capacity_kwh": 27,
        "battery_target_percent": 90,
        "forecast_trust_percent": 80,
    }
    result = await _walk_options(hass, config_entry, pages[:4])

    assert result["step_id"] == "forecast"
    assert result["errors"] == {"base": "invalid_energy_unit"}


async def test_options_flow_stores_ev_first_inputs(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Complete forecast inputs are saved with the other pages."""
    config_entry.add_to_hass(hass)
    hass.states.async_set("sensor.forecast", "10", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.level", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.house", "400", {"unit_of_measurement": "W"})
    pages = _pages(config_entry.options)
    pages[3] = {
        "forecast_remaining_entity": "sensor.forecast",
        "battery_level_entity": "sensor.level",
        "house_power_entity": "sensor.house",
        "battery_capacity_kwh": 27,
        "battery_target_percent": 85,
        "forecast_trust_percent": 70,
    }
    result = await _walk_options(hass, config_entry, pages)

    assert result["type"] == "create_entry"
    assert result["data"]["forecast_remaining_entity"] == "sensor.forecast"
    assert result["data"]["battery_target_percent"] == 85
    assert result["data"]["grid_power_entity"] == "sensor.grid_power"


async def test_options_flow_prefills_stored_values(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The first options page is prefilled from the stored options."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["step_id"] == "init"
    keys = {str(marker): marker for marker in result["data_schema"].schema}
    assert keys["grid_power_entity"].description["suggested_value"] == "sensor.grid_power"


async def test_offpeak_windows_are_stored_as_a_list(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Flat window form fields are collapsed into the stored window list."""
    config_entry.add_to_hass(hass)
    pages = _pages(
        config_entry.options,
        offpeak_window_1_start="23:00:00",
        offpeak_window_1_end="06:00:00",
        offpeak_window_1_days="weekdays",
    )
    result = await _walk_options(hass, config_entry, pages)

    assert result["data"][CONF_OFFPEAK_WINDOWS] == [{"start": "23:00", "end": "06:00", "days": "weekdays"}]


async def test_incomplete_offpeak_window_is_rejected(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """A window with only a start time shows an error on the off-peak page."""
    config_entry.add_to_hass(hass)
    result = await _walk_options(hass, config_entry, _pages(config_entry.options, offpeak_window_1_start="23:00:00"))

    assert result["step_id"] == "offpeak"
    assert result["errors"] == {"base": "offpeak_window_incomplete"}


async def test_pages_offer_next_then_submit_and_go_back(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Only the last page is a final step, and going back returns to the previous page with values kept."""
    pages = _pages(config_entry.options)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "go_back" not in {str(key) for key in result["data_schema"].schema}
    assert result["last_step"] is False

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=pages[0])
    assert result["step_id"] == "solar"
    assert "go_back" in {str(key) for key in result["data_schema"].schema}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={**pages[1], "solar_start_w": 1500, "go_back": True},
    )
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    keys = {str(marker): marker for marker in result["data_schema"].schema}
    assert keys["grid_power_entity"].description["suggested_value"] == "sensor.grid_power"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=pages[0])
    keys = {str(marker): marker for marker in result["data_schema"].schema}
    assert result["step_id"] == "solar"
    assert keys["solar_start_w"].default() == 1500

    for page_input in pages[1:4]:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=page_input)
    assert result["step_id"] == "offpeak"
    assert result["last_step"] is True
