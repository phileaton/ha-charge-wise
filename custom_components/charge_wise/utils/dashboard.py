"""Create and remove the sidebar dashboard that Charge Wise can generate for each entry.

Home Assistant offers integrations no API to add a dashboard, so this writes the same storage records the dashboard
editor writes and registers the sidebar panel live. Dashboards created this way are re-applied on every setup, which
restores one that the dashboard editor dropped from its own records.
"""

import logging
from typing import Any

from custom_components.charge_wise.const import CONF_CHARGER_POWER_ENTITY, CONF_SOLAR_POWER_ENTITY, DOMAIN, POWER_TO_W
from custom_components.charge_wise.utils.dashboard_layout import build_view
from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

_REGISTRY_KEY = "lovelace_dashboards"
_REGISTRY_VERSION = 1
_ICON = "mdi:ev-station"

_CONTROLS = (
    ("switch", "enabled"),
    ("switch", "solar_enabled"),
    ("select", "ev_first_mode"),
    ("select", "offpeak_mode"),
    ("switch", "manual_override"),
    ("number", "manual_current"),
    ("number", "offpeak_current"),
)
_OWN_ENTITIES = (
    *_CONTROLS,
    ("sensor", "controller_status"),
    ("sensor", "decision_reason"),
    ("sensor", "restart_cooldown_end"),
    ("sensor", "requested_current"),
    ("sensor", "available_solar_budget"),
    ("sensor", "house_load"),
    ("sensor", "average_house_load"),
    ("sensor", "battery_need"),
    ("sensor", "forecast_surplus"),
    ("sensor", "forecast_accuracy"),
    ("sensor", "next_offpeak_window"),
    ("binary_sensor", "ev_first_active"),
    ("binary_sensor", "ev_under_drawing"),
    ("binary_sensor", "vehicle_connected"),
    ("binary_sensor", "vehicle_charging"),
)


def _entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Return the registered entity IDs of this entry by key, leaving out any that do not exist."""
    registry = er.async_get(hass)
    found = {
        key: registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        for platform, key in _OWN_ENTITIES
    }
    return {key: entity_id for key, entity_id in found.items() if entity_id}


def _budget_in_kw(hass: HomeAssistant, entity_id: str | None) -> bool:
    """Return whether the solar budget sensor reports kW, which is what new installs get."""
    if entity_id is None:
        return True
    if (state := hass.states.get(entity_id)) is not None and (unit := state.attributes.get("unit_of_measurement")):
        return unit == "kW"
    registry_entry = er.async_get(hass).async_get(entity_id)
    return registry_entry is None or registry_entry.unit_of_measurement in (None, "kW")


def _power_scale_to_kw(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return the conversion from a power sensor's native unit to kW, if it is known."""
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    unit = state.attributes.get("unit_of_measurement") if state is not None else None
    if unit is None:
        registry_entry = er.async_get(hass).async_get(entity_id)
        unit = registry_entry.unit_of_measurement if registry_entry is not None else None
    if not isinstance(unit, str) or (factor := POWER_TO_W.get(unit)) is None:
        return None
    return factor / 1000


def build_config(hass: HomeAssistant, entry: ConfigEntry, vehicle_labels: dict[str, str]) -> dict[str, Any]:
    """Build the dashboard from the entities this entry registered."""
    ids = _entity_ids(hass, entry)
    view = build_view(
        entry.title,
        ids,
        entry.options,
        tuple(key for _, key in _CONTROLS),
        vehicle_labels=vehicle_labels,
        budget_in_kw=_budget_in_kw(hass, ids.get("available_solar_budget")),
        charger_power_scale_to_kw=_power_scale_to_kw(hass, entry.options.get(CONF_CHARGER_POWER_ENTITY)),
        solar_power_scale_to_kw=_power_scale_to_kw(hass, entry.options.get(CONF_SOLAR_POWER_ENTITY)),
    )
    return {"views": [view]}


def _url_path(entry: ConfigEntry) -> str:
    """Return a dashboard URL path, which Home Assistant requires to contain a hyphen."""
    slug = slugify(entry.title, separator="-")
    return slug if "-" in slug else f"charge-wise-{slug}"


async def _load_registry(hass: HomeAssistant) -> tuple[Store[dict[str, Any]], dict[str, Any]]:
    """Open the dashboard records Home Assistant keeps in storage."""
    store: Store[dict[str, Any]] = Store(hass, _REGISTRY_VERSION, _REGISTRY_KEY)
    data = await store.async_load() or {}
    data.setdefault("items", [])
    return store, data


async def async_ensure_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create or refresh this entry's dashboard and show it in the sidebar."""
    if (lovelace := hass.data.get(LOVELACE_DATA)) is None:
        return False

    store, data = await _load_registry(hass)
    items: list[dict[str, Any]] = data["items"]
    item = next((i for i in items if i.get("id") == entry.entry_id), None)
    url_path = item["url_path"] if item else _url_path(entry)

    if item is None:
        if any(i.get("url_path") == url_path for i in items) or url_path in lovelace.dashboards:
            _LOGGER.warning("A dashboard at /%s already exists, so Charge Wise did not create its own", url_path)
            return False
        item = {
            "id": entry.entry_id,
            "url_path": url_path,
            "mode": "storage",
            "require_admin": False,
            "show_in_sidebar": True,
        }
        items.append(item)
    item.update({"title": entry.title, "icon": _ICON})
    await store.async_save(data)

    dashboard = lovelace.dashboards.get(url_path)
    if dashboard is None:
        dashboard = lovelace.dashboards[url_path] = LovelaceStorage(hass, item)
    translations = await async_get_translations(hass, hass.config.language, "selector", {DOMAIN})
    prefix = f"component.{DOMAIN}.selector.vehicle_dashboard.options."
    vehicle_labels = {key.removeprefix(prefix): value for key, value in translations.items() if key.startswith(prefix)}
    await dashboard.async_save(build_config(hass, entry, vehicle_labels))

    panel: dict[str, Any] = {
        "frontend_url_path": url_path,
        "require_admin": item["require_admin"],
        "show_in_sidebar": item["show_in_sidebar"],
        "sidebar_title": item["title"],
        "sidebar_icon": item["icon"],
        "config": {"mode": "storage"},
    }
    try:
        frontend.async_register_built_in_panel(hass, "lovelace", **panel)
    except ValueError:
        frontend.async_register_built_in_panel(hass, "lovelace", update=True, **panel)
    return True


async def async_remove_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove this entry's dashboard, if Charge Wise created one."""
    store, data = await _load_registry(hass)
    items: list[dict[str, Any]] = data["items"]
    if (item := next((i for i in items if i.get("id") == entry.entry_id), None)) is None:
        return

    url_path = item["url_path"]
    items.remove(item)
    await store.async_save(data)

    if (lovelace := hass.data.get(LOVELACE_DATA)) is not None and (
        dashboard := lovelace.dashboards.pop(url_path, None)
    ):
        await dashboard.async_delete()
    frontend.async_remove_panel(hass, url_path, warn_if_unknown=False)
