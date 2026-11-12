"""Integration tests for charger-managed solar handoff."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    setup_test_component_platform,
)

from custom_components.charge_wise.const import DOMAIN
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util


class ChargerSwitch(SwitchEntity):
    """A charger switch that reports commands immediately."""

    _attr_name = "Charger Enable"
    _attr_unique_id = "native_test_charger"
    _attr_is_on = False

    async def async_turn_on(self, **kwargs: object) -> None:
        """Enable the charger."""
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        """Disable the charger."""
        self._attr_is_on = False
        self.async_write_ha_state()


class SessionLimit(NumberEntity):
    """A session limit that reports accepted commands."""

    _attr_name = "Current Limit"
    _attr_unique_id = "native_test_current"
    _attr_native_unit_of_measurement = "A"
    _attr_native_value = 6
    _attr_native_min_value = 6
    _attr_native_max_value = 32
    _attr_native_step = 1

    async def async_set_native_value(self, value: float) -> None:
        """Publish the accepted limit."""
        self._attr_native_value = value
        self.async_write_ha_state()


class ChargerSolar(SelectEntity):
    """A solar-mode control that can delay command confirmation."""

    _attr_name = "Charger Solar"
    _attr_unique_id = "native_test_solar"
    _attr_options = ["Off", "Eco", "Full solar"]
    _attr_current_option = "Off"

    def __init__(self) -> None:
        """Initialize command tracking."""
        self.commands: list[str] = []
        self.delay = False

    async def async_select_option(self, option: str) -> None:
        """Apply or defer a charger mode command."""
        self.commands.append(option)
        if not self.delay:
            self._attr_current_option = option
            self.async_write_ha_state()

    def confirm(self, option: str) -> None:
        """Publish the charger's delayed response."""
        self._attr_current_option = option
        self.async_write_ha_state()


@pytest.fixture
async def native_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> tuple[MockConfigEntry, ChargerSolar]:
    """Load real Charge Wise entities alongside controllable charger entities."""
    charger = ChargerSwitch()
    solar = ChargerSolar()
    hass.states.async_remove("switch.charger_enable")
    hass.states.async_remove("number.current_limit")
    setup_test_component_platform(hass, "number", [SessionLimit()])
    assert await async_setup_component(hass, "number", {"number": [{"platform": "test"}]})
    setup_test_component_platform(hass, "switch", [charger])
    setup_test_component_platform(hass, "select", [solar])
    assert await async_setup_component(hass, "switch", {"switch": [{"platform": "test"}]})
    assert await async_setup_component(hass, "select", {"select": [{"platform": "test"}]})
    hass.states.async_set("sensor.forecast_remaining", "20", {"unit_of_measurement": "kWh"})
    hass.states.async_set("sensor.battery_level", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.solar_production", "500", {"unit_of_measurement": "W"})
    hass.states.async_set(
        "sun.sun", "above_horizon", {"next_setting": (dt_util.utcnow() + timedelta(hours=6)).isoformat()}
    )
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            **config_entry.options,
            "native_solar_entity": "select.charger_solar",
            "native_solar_option": "Full solar",
            "native_solar_off_option": "Off",
            "native_solar_release_percent": 97,
            "forecast_remaining_entity": "sensor.forecast_remaining",
            "battery_level_entity": "sensor.battery_level",
            "solar_power_entity": "sensor.solar_production",
            "battery_capacity_kwh": 27,
            "cooldown_s": 0,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry, solar


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None
    return entity_id


async def _switch(hass: HomeAssistant, entry: MockConfigEntry, key: str, on: bool = True) -> None:
    await hass.services.async_call(
        "switch",
        "turn_on" if on else "turn_off",
        {"entity_id": _entity_id(hass, entry, "switch", key)},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_native_solar_handoff_and_manual_override(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """Native solar owns current until manual override takes the charger back."""
    entry, solar = native_entry
    calls = async_capture_events(hass, "call_service")
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    reason = _entity_id(hass, entry, "sensor", "decision_reason")
    assert hass.states.get(reason).state == "native_solar"
    assert hass.states.get("switch.charger_enable").state == "on"
    assert solar.commands == ["Full solar"]
    assert float(hass.states.get("number.current_limit").state) == 32
    charger_calls = [
        (event.data["domain"], event.data["service"])
        for event in calls
        if event.data["service_data"].get("entity_id")
        in ("number.current_limit", "switch.charger_enable", "select.charger_solar")
    ]
    assert charger_calls == [("number", "set_value"), ("select", "select_option"), ("switch", "turn_on")]

    await _switch(hass, entry, "manual_override")
    assert solar.commands == ["Full solar", "Off"]
    assert hass.states.get(reason).state == "manual"
    assert hass.states.get("switch.charger_enable").state == "on"


async def test_native_handoff_resets_limit_before_disabling_control(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """An active manual session releases its limit before Wallbox takes over."""
    entry, solar = native_entry
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    await _switch(hass, entry, "manual_override")
    hass.states.async_set("number.hardware_maximum", "24")
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _entity_id(hass, entry, "number", "manual_current"), "value": 10},
        blocking=True,
    )
    await hass.async_block_till_done()
    calls = async_capture_events(hass, "call_service")
    await _switch(hass, entry, "manual_override", on=False)
    charger_calls = [
        (event.data["domain"], event.data["service"])
        for event in calls
        if event.data["service_data"].get("entity_id")
        in ("number.current_limit", "switch.charger_enable", "select.charger_solar")
    ]
    assert charger_calls == [
        ("number", "set_value"),
        ("switch", "turn_off"),
        ("select", "select_option"),
        ("switch", "turn_on"),
    ]
    assert float(hass.states.get("number.current_limit").state) == 24
    assert hass.states.get("switch.charger_enable").state == "on"
    assert solar.commands == ["Full solar", "Off", "Full solar"]
    hass.states.async_set("sensor.grid_power", "-1000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get("switch.charger_enable").state == "on"


async def test_unavailable_session_limit_prevents_native_handoff(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """Do not select native solar when its session limit cannot be released."""
    entry, solar = native_entry
    hass.states.async_set("number.current_limit", "unavailable")
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    assert solar.commands == []
    assert hass.states.get("switch.charger_enable").state == "off"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "decision_reason")).state == "control_failed"


async def test_delayed_native_mode_confirmation_does_not_race_manual_override(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """An unconfirmed solar command must settle before a conflicting mode is enabled."""
    entry, solar = native_entry
    solar.delay = True
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    assert solar.commands == ["Full solar"]
    assert hass.states.get("switch.charger_enable").state == "off"
    await _switch(hass, entry, "manual_override")
    assert solar.commands == ["Full solar"]
    assert hass.states.get("switch.charger_enable").state == "off"
    solar.delay = False
    solar.confirm("Full solar")
    await hass.async_block_till_done()
    assert solar.commands == ["Full solar", "Off"]
    assert hass.states.get("switch.charger_enable").state == "on"


async def test_unavailable_native_control_stops_the_charger(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """An unavailable native control fails safe and reports the control error."""
    entry, solar = native_entry
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    hass.states.async_set("select.charger_solar", "unavailable", {"options": ["Off", "Full solar"]})
    await hass.async_block_till_done()
    assert hass.states.get("switch.charger_enable").state == "off"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "decision_reason")).state == "control_failed"
    solar.confirm("Full solar")
    await hass.async_block_till_done()
    await _switch(hass, entry, "enabled", on=False)


async def test_unloading_releases_native_control(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """Unloading first stops charging and turns off the charger's solar mode."""
    entry, solar = native_entry
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    assert hass.states.get("switch.charger_enable").state == "on"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert hass.states.get("switch.charger_enable").state == "off"
    assert solar.commands == ["Full solar", "Off"]


async def test_removing_native_control_requires_a_confirmed_safe_release(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """An options update cannot lose control of a charger that is still in native mode."""
    entry, _ = native_entry
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "charger"})
    charger = {
        key: entry.options[key]
        for key in (
            "grid_power_entity",
            "charger_power_entity",
            "charger_switch_entity",
            "current_target_entity",
            "minimum_current_a",
            "maximum_current_a",
            "voltage_v",
        )
    }
    for page in (charger, {}, {}, {}, {}):
        result = await hass.config_entries.options.async_configure(result["flow_id"], user_input=page)
    assert result["step_id"] == "offpeak"
    assert result["errors"] == {"base": "native_solar_release_required"}
    await _switch(hass, entry, "enabled", on=False)
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={})
    assert result["type"] == "create_entry"


async def test_full_battery_handoff_releases_below_configured_threshold(
    hass: HomeAssistant, native_entry: tuple[MockConfigEntry, ChargerSolar]
) -> None:
    """Full-battery handoff is held above the release threshold while EV-first remains active."""
    entry, solar = native_entry
    ev_first = _entity_id(hass, entry, "select", "ev_first_mode")
    await _switch(hass, entry, "enabled")
    await hass.services.async_call("select", "select_option", {"entity_id": ev_first, "option": "on"}, blocking=True)
    await _switch(hass, entry, "solar_enabled")
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "ev_first_active")).state == "on"
    assert solar.commands == []
    for level in ("100", "98", "97"):
        hass.states.async_set("sensor.battery_level", level, {"unit_of_measurement": "%"})
        await hass.async_block_till_done()
        assert hass.states.get("select.charger_solar").state == "Full solar"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    assert hass.states.get("select.charger_solar").state == "Full solar"
    hass.states.async_set("sensor.battery_level", "96", {"unit_of_measurement": "%"})
    await hass.async_block_till_done()
    assert hass.states.get("select.charger_solar").state == "Off"


@pytest.mark.parametrize("confirms_limit", [True, False])
async def test_native_handoff_bounds_current_confirmation(
    hass: HomeAssistant,
    native_entry: tuple[MockConfigEntry, ChargerSolar],
    freezer: FrozenDateTimeFactory,
    confirms_limit: bool,
) -> None:
    """A slow or ignored current-limit command must not be spammed during native handoff."""
    entry, solar = native_entry
    commands: list[float] = []

    async def delay_current(call: ServiceCall) -> None:
        commands.append(call.data["value"])

    hass.services.async_register("number", "set_value", delay_current)
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    for power in (-1000, -1100, -1200):
        hass.states.async_set("sensor.grid_power", power, {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
    assert commands == [32]
    assert solar.commands == []
    assert hass.states.get("switch.charger_enable").state == "off"
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    if confirms_limit:
        state = hass.states.get("number.current_limit")
        hass.states.async_set("number.current_limit", "32", dict(state.attributes))
        await hass.async_block_till_done()
    freezer.tick(21)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    status = _entity_id(hass, entry, "sensor", "controller_status")
    assert hass.states.get(status).state == ("waiting" if confirms_limit else "error")
    assert solar.commands == (["Full solar"] if confirms_limit else [])
    assert commands == [32]
    assert hass.states.get("switch.charger_enable").state == ("on" if confirms_limit else "off")


async def test_native_current_limit_changes_do_not_extend_the_response_deadline(
    hass: HomeAssistant,
    native_entry: tuple[MockConfigEntry, ChargerSolar],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A changed hardware cap replaces the target without keeping an ignored handoff alive."""
    entry, solar = native_entry
    commands: list[float] = []

    async def delay_current(call: ServiceCall) -> None:
        commands.append(call.data["value"])

    hass.services.async_register("number", "set_value", delay_current)
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    freezer.tick(25)
    hass.states.async_set("number.hardware_maximum", "24", {"unit_of_measurement": "A"})
    await hass.async_block_till_done()
    assert commands == [32, 24]
    freezer.tick(6)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass, entry, "sensor", "controller_status")).state == "error"
    assert commands == [32, 24]
    assert solar.commands == []
    assert hass.states.get("switch.charger_enable").state == "off"


async def test_disabling_native_handoff_cancels_its_current_confirmation(
    hass: HomeAssistant,
    native_entry: tuple[MockConfigEntry, ChargerSolar],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A deliberate disable and re-enable starts a fresh handoff confirmation window."""
    entry, solar = native_entry
    commands: list[float] = []

    async def delay_current(call: ServiceCall) -> None:
        commands.append(call.data["value"])

    hass.services.async_register("number", "set_value", delay_current)
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    freezer.tick(20)
    await _switch(hass, entry, "enabled", on=False)
    freezer.tick(15)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass, entry, "sensor", "controller_status")).state == "off"
    await _switch(hass, entry, "enabled")
    assert hass.states.get(_entity_id(hass, entry, "sensor", "controller_status")).state == "waiting"
    assert commands == [32, 32]
    assert solar.commands == []


@pytest.mark.parametrize("confirms_stop", [True, False])
async def test_native_handoff_requires_a_bounded_stop_confirmation(
    hass: HomeAssistant,
    native_entry: tuple[MockConfigEntry, ChargerSolar],
    freezer: FrozenDateTimeFactory,
    confirms_stop: bool,
) -> None:
    """An ignored stop must report an error without changing ownership of a running charger."""
    entry, solar = native_entry
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    stops: list[str] = []

    async def delay_stop(call: ServiceCall) -> None:
        stops.append(call.data["entity_id"])

    hass.services.async_register("switch", "turn_off", delay_stop)
    await _switch(hass, entry, "manual_override")
    for power in (-1000, -1100, -1200):
        hass.states.async_set("sensor.grid_power", power, {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
    assert stops == ["switch.charger_enable"]
    assert solar.commands == ["Full solar"]
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    if confirms_stop:
        hass.states.async_set("switch.charger_enable", "off")
        await hass.async_block_till_done()
    freezer.tick(21)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    status = _entity_id(hass, entry, "sensor", "controller_status")
    assert hass.states.get(status).state == ("charging" if confirms_stop else "error")
    assert solar.commands == (["Full solar", "Off"] if confirms_stop else ["Full solar"])
    assert len(stops) == (1 if confirms_stop else 2)
    hass.states.async_set("sensor.grid_power", "-1300", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert hass.states.get(status).state == ("charging" if confirms_stop else "error")
    assert len(stops) == (1 if confirms_stop else 2)
    if not confirms_stop:
        hass.states.async_set("switch.charger_enable", "off")
        await hass.async_block_till_done()
    assert solar.commands == ["Full solar", "Off"]
    assert hass.states.get(status).state == ("charging" if confirms_stop else "error")
    assert hass.states.get("switch.charger_enable").state == ("on" if confirms_stop else "off")


@pytest.mark.parametrize("late_reply", [True, False])
@pytest.mark.parametrize("input_update", [True, False])
async def test_native_mode_timeout_allows_an_explicit_retry(
    hass: HomeAssistant,
    native_entry: tuple[MockConfigEntry, ChargerSolar],
    freezer: FrozenDateTimeFactory,
    late_reply: bool,
    input_update: bool,
) -> None:
    """Expired mode commands must not poison manual recovery or permit an automatic restart."""
    entry, solar = native_entry
    solar.delay = True
    await _switch(hass, entry, "enabled")
    await _switch(hass, entry, "solar_enabled")
    try:
        freezer.tick(25)
        if input_update:
            hass.states.async_set("sensor.grid_power", "-1000", {"unit_of_measurement": "W"})
            await hass.async_block_till_done()
        freezer.tick(6)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        status = _entity_id(hass, entry, "sensor", "controller_status")
        assert hass.states.get(status).state == "error"
        assert hass.states.get("switch.charger_enable").state == "off"
        solar.delay = False
        if late_reply:
            solar.confirm("Full solar")
            await hass.async_block_till_done()
        assert hass.states.get(status).state == "error"
        assert hass.states.get("switch.charger_enable").state == "off"
        await _switch(hass, entry, "enabled", on=False)
        assert hass.states.get(status).state == "off"
        await _switch(hass, entry, "enabled")
        assert hass.states.get(status).state == "waiting"
        assert hass.states.get("select.charger_solar").state == "Full solar"
        assert hass.states.get("switch.charger_enable").state == "on"
        assert solar.commands == (["Full solar", "Off", "Full solar"] if late_reply else ["Full solar", "Full solar"])
    finally:
        solar.delay = False
        solar.confirm("Full solar")
        await hass.async_block_till_done()
        await _switch(hass, entry, "enabled", on=False)
