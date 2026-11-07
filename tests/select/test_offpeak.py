"""Tests for recurring and one-time off-peak charging."""

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.charge_wise.const import CONF_OFFPEAK_WINDOWS, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er


def _entity(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    """Resolve one registered entity belonging to the test entry."""
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None
    return entity_id


async def _select(hass: HomeAssistant, entry: MockConfigEntry, mode: str) -> str:
    """Select a mode through Home Assistant's service."""
    entity_id = _entity(hass, entry, "select", "offpeak_mode")
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": mode},
        blocking=True,
    )
    await hass.async_block_till_done()
    return entity_id


async def _move(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: str) -> None:
    """Advance time and deliver due Home Assistant timers."""
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.parametrize("selected_at", ["2026-01-07 07:00:00Z", "2026-01-07 11:00:00Z"])
async def test_on_once_expires_at_end_of_current_or_next_period(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    selected_at: str,
) -> None:
    """One-time mode expires on schedule even with the master switch off."""
    await _move(hass, freezer, selected_at)
    mode = await _select(hass, init_integration, "on_once")
    active = _entity(hass, init_integration, "binary_sensor", "offpeak_active")
    await _move(hass, freezer, "2026-01-07 13:59:59Z")
    assert hass.states.get(mode).state == "on_once"
    await _move(hass, freezer, "2026-01-07 14:00:00Z")
    assert hass.states.get(mode).state == "off"
    assert hass.states.get(active).state == "off"
    await _move(hass, freezer, "2026-01-08 09:00:00Z")
    assert hass.states.get(mode).state == "off"


@pytest.mark.parametrize(
    ("restart_at", "expected"),
    [("2026-01-07 12:00:00Z", "on_once"), ("2026-01-08 09:00:00Z", "off")],
)
async def test_restart_keeps_original_one_time_deadline(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    restart_at: str,
    expected: str,
) -> None:
    """Reloading restores a pending request but never arms another period after expiry."""
    await _move(hass, freezer, "2026-01-07 11:00:00Z")
    mode = await _select(hass, init_integration, "on_once")
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    await _move(hass, freezer, restart_at)
    assert await hass.config_entries.async_setup(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(mode).state == expected
    if expected == "on_once":
        await _move(hass, freezer, "2026-01-07 14:00:00Z")
        assert hass.states.get(mode).state == "off"


@pytest.mark.parametrize("replacement", ["off", "on"])
async def test_changing_mode_cancels_one_time_expiry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    replacement: str,
) -> None:
    """Explicit Off or recurring On supersedes a pending one-time request and survives reload."""
    await _move(hass, freezer, "2026-01-07 11:00:00Z")
    mode = await _select(hass, init_integration, "on_once")
    await _select(hass, init_integration, replacement)
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    await _move(hass, freezer, "2026-01-07 14:00:00Z")
    assert hass.states.get(mode).state == replacement
    await _move(hass, freezer, "2026-01-08 09:00:00Z")
    assert hass.states.get(mode).state == replacement


async def test_on_once_requires_a_schedule(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """An empty schedule cannot leave a one-time request enabled forever."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={**config_entry.options, CONF_OFFPEAK_WINDOWS: []})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError, match="Configure an off-peak window"):
        await _select(hass, config_entry, "on_once")
    mode = _entity(hass, config_entry, "select", "offpeak_mode")
    assert hass.states.get(mode).state == "off"


async def test_old_offpeak_switch_is_removed(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """The removed switch does not remain as an unavailable registry entity."""
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"{config_entry.entry_id}_offpeak_enabled",
        config_entry=config_entry,
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(old.entity_id) is None
    mode = _entity(hass, config_entry, "select", "offpeak_mode")
    assert hass.states.get(mode).state == "off"
