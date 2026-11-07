"""Normalize charger status vocabularies without inferring connection from silence."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any

from custom_components.charge_wise.const import CONF_CHARGER_STATUS_ENTITY, CONF_EV_CONNECTED_ENTITY


class ChargerSessionStatus(StrEnum):
    """Session information explicitly reported by a charger."""

    DISCONNECTED = "disconnected"
    IDLE = "idle"
    CHARGING = "charging"
    PAUSED = "paused"
    FINISHED = "finished"
    FAULT = "fault"


@dataclass(frozen=True)
class ChargerObservation:
    """Independent physical connection, charging activity and session evidence."""

    connected: bool | None = None
    charging: bool | None = None
    session: ChargerSessionStatus | None = None
    profile: str = "unknown"
    raw_status: str | None = None


OCPP_STATUSES: dict[str, ChargerSessionStatus] = {
    "available": ChargerSessionStatus.DISCONNECTED,
    "preparing": ChargerSessionStatus.IDLE,
    "charging": ChargerSessionStatus.CHARGING,
    "suspendedev": ChargerSessionStatus.PAUSED,
    "suspendedevse": ChargerSessionStatus.PAUSED,
    "faulted": ChargerSessionStatus.FAULT,
    "finishing": ChargerSessionStatus.FINISHED,
}
WALLBOX_STATUSES: dict[str, ChargerSessionStatus] = {
    "locked": ChargerSessionStatus.DISCONNECTED,
    "ready": ChargerSessionStatus.DISCONNECTED,
    "locked, car connected": ChargerSessionStatus.IDLE,
    "charging": ChargerSessionStatus.CHARGING,
    "paused": ChargerSessionStatus.PAUSED,
    "scheduled": ChargerSessionStatus.IDLE,
    "waiting for car demand": ChargerSessionStatus.IDLE,
    "error": ChargerSessionStatus.FAULT,
}
PROFILES = ("auto", "ocpp", "wallbox", "custom")
CUSTOM_STATUS_KEYS = tuple(f"charger_states_{status.value}" for status in ChargerSessionStatus)
_RESERVED = {"", "unknown", "unavailable", "none"}


def normalize_status(value: str) -> str:
    """Match state values independent of surrounding whitespace and case."""
    return value.strip().casefold()


def valid_custom_mapping(groups: Mapping[str, Sequence[str]]) -> bool:
    """Reject ambiguous groups and values representing missing data."""
    seen: set[str] = set()
    for key in CUSTOM_STATUS_KEYS:
        values = groups.get(key, ())
        if isinstance(values, str) or not isinstance(values, (list, tuple)):
            return False
        for value in values:
            if not isinstance(value, str):
                return False
            normalized = normalize_status(value)
            if normalized in _RESERVED or normalized in seen:
                return False
            seen.add(normalized)
    return bool(seen)


def classify_status(
    value: str | None,
    profile: str,
    groups: Mapping[str, Sequence[str]] | None = None,
) -> ChargerObservation:
    """Interpret only statuses with an established meaning for the selected profile.

    OCPP Finishing and Unavailable do not establish physical connection. Wallbox
    Disconnected describes communication loss and is likewise left unknown.
    """
    if value is None or normalize_status(value) in _RESERVED:
        return ChargerObservation(profile=profile, raw_status=value)
    mapping = OCPP_STATUSES if profile == "ocpp" else WALLBOX_STATUSES if profile == "wallbox" else {}
    if profile == "custom" and groups is not None and valid_custom_mapping(groups):
        mapping = {
            normalize_status(raw): status
            for status in ChargerSessionStatus
            for raw in groups.get(f"charger_states_{status.value}", ())
        }
    session = mapping.get(normalize_status(value))
    connected = None if session in (None, ChargerSessionStatus.FAULT) else session != ChargerSessionStatus.DISCONNECTED
    if profile == "ocpp" and normalize_status(value) == "finishing":
        connected = None
    charging = None if session in (None, ChargerSessionStatus.FAULT) else session == ChargerSessionStatus.CHARGING
    if profile == "ocpp" and normalize_status(value) == "preparing":
        charging = None
    return ChargerObservation(connected, charging, session, profile, value)


class ChargingPowerDetector:
    """Detect measured charging with 100 W start and 50 W stop thresholds."""

    def __init__(self) -> None:
        """Start without a measured charging state."""
        self.charging: bool | None = None

    def update(self, power_w: float | None) -> bool | None:
        """Reset on invalid data, retaining hysteresis only across valid samples."""
        if power_w is None or not isfinite(power_w) or power_w < 0:
            self.charging = None
        elif power_w >= 100:
            self.charging = True
        elif power_w <= 50:
            self.charging = False
        return self.charging


def charger_status_source(options: Mapping[str, Any]) -> str | None:
    """Use the unified source, falling back to an older entry's connection selection."""
    return options.get(CONF_CHARGER_STATUS_ENTITY) or options.get(CONF_EV_CONNECTED_ENTITY)
