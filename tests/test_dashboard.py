"""Tests for the generated Charge Wise dashboard."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import CONF_CREATE_DASHBOARD
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.lovelace import LovelaceData
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

URL_PATH = "test-charger"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, *, create: bool) -> None:
    hass.data[LOVELACE_DATA] = LovelaceData(
        resource_mode="storage",
        dashboards={},
        resources=None,  # type: ignore[arg-type]
        yaml_dashboards={},
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_CREATE_DASHBOARD: create})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_dashboard_is_created_with_the_entry_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """The opted-in dashboard lists this entry's real entities."""
    await _setup(hass, config_entry, create=True)

    dashboard = hass.data[LOVELACE_DATA].dashboards[URL_PATH]
    config = await dashboard.async_load(False)
    controls, status, history = config["views"][0]["cards"]
    assert URL_PATH in hass.data[DATA_PANELS]
    assert any(entity.startswith("switch.test_charger") for entity in controls["entities"])
    assert len(controls["entities"]) == 7
    assert "sensor.test_charger_controller_status" in status["entities"]
    assert history["type"] == "history-graph"
    assert "binary_sensor.test_charger_battery_protection_active" in status["entities"]


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
