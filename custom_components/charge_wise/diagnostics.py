"""
Diagnostics support for charge_wise.

https://developers.home-assistant.io/docs/core/integration_diagnostics
"""

from collections.abc import Mapping
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.redact import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import ChargeWiseConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "access_token",
    "api_key",
    "charger_charging_source",
    "charger_connection_source",
    "charger_raw_status",
    "email",
    "id",
    "latitude",
    "longitude",
    "name",
    "refresh_token",
    "serial_number",
    "token",
}


def _redaction_keys(value: Any) -> set[str]:
    """Find entity-reference keys in nested options without exporting their values."""
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.endswith("_entity"):
                keys.add(key)
            keys.update(_redaction_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_redaction_keys(child))
    return keys


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ChargeWiseConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a config entry.

    Returns:
        The redacted entry configuration and the current coordinator state.

    """
    coordinator = entry.runtime_data.coordinator
    to_redact = TO_REDACT | _redaction_keys(entry.data) | _redaction_keys(entry.options)

    return {
        "entry": {
            "version": entry.version,
            "minor_version": entry.minor_version,
            "state": str(entry.state),
            "data": async_redact_data(entry.data, to_redact),
            "options": async_redact_data(entry.options, to_redact),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "last_exception": type(coordinator.last_exception).__name__ if coordinator.last_exception else None,
            "data": async_redact_data(asdict(coordinator.data), to_redact),
        },
    }
