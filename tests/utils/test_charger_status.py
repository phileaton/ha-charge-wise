"""Tests for conservative charger status classification and measured activity."""

import pytest

from custom_components.charge_wise.utils.charger_status import (
    ChargingPowerDetector,
    classify_status,
    valid_custom_mapping,
)


@pytest.mark.parametrize(
    ("profile", "raw", "connected", "session"),
    [
        ("ocpp", "Available", False, "disconnected"),
        ("ocpp", "Preparing", True, "idle"),
        ("ocpp", "Charging", True, "charging"),
        ("ocpp", "SuspendedEV", True, "paused"),
        ("ocpp", "SuspendedEVSE", True, "paused"),
        ("ocpp", "Finishing", True, "finished"),
        ("ocpp", "Reserved", None, None),
        ("ocpp", "Faulted", None, "fault"),
        ("wallbox", "Locked", False, "disconnected"),
        ("wallbox", "  LOCKED, CAR CONNECTED  ", True, "idle"),
        ("wallbox", "Charging", True, "charging"),
        ("wallbox", "Paused", True, "paused"),
        ("wallbox", "Disconnected", None, None),
        ("wallbox", "Error", None, "fault"),
        ("wallbox", "Updating", None, None),
        ("ocpp", "future status", None, None),
        ("wallbox", "unavailable", None, None),
        ("ocpp", "unknown", None, None),
        ("unknown", "Charging", None, None),
    ],
)
def test_profile_statuses(profile: str, raw: str, connected: bool | None, session: str | None) -> None:
    """Only explicit source-specific evidence establishes a connection."""
    observation = classify_status(raw, profile)
    assert observation.connected is connected
    assert observation.session == session
    assert observation.raw_status == raw


@pytest.mark.parametrize(
    "groups",
    [
        {},
        {"charger_states_idle": ["unknown"]},
        {"charger_states_idle": ["unavailable"]},
        {"charger_states_idle": [""]},
        {"charger_states_idle": ["Ready"], "charger_states_disconnected": [" ready "]},
        {"charger_states_idle": "ready"},
    ],
)
def test_reject_ambiguous_custom_mappings(groups: dict[str, object]) -> None:
    """An invalid custom configuration cannot create a positive connection signal."""
    assert not valid_custom_mapping(groups)
    assert classify_status("ready", "custom", groups).connected is None


def test_custom_finished_and_fault() -> None:
    """Finished is explicit session evidence; fault does not establish connection."""
    groups = {"charger_states_finished": ["Done"], "charger_states_fault": ["Broken"]}
    finished = classify_status("done", "custom", groups)
    assert finished.connected is True
    assert finished.charging is False
    assert finished.session == "finished"
    assert classify_status("broken", "custom", groups).connected is None


def test_charging_hysteresis_and_invalid_measurement() -> None:
    """Noise around a threshold does not flicker, and missing watts reset history."""
    detector = ChargingPowerDetector()
    assert detector.update(75) is None
    assert detector.update(100) is True
    assert detector.update(75) is True
    assert detector.update(50) is False
    assert detector.update(75) is False
    for value in (None, float("nan"), float("inf"), -1):
        assert detector.update(200) is True
        assert detector.update(value) is None
        assert detector.update(75) is None


def test_ocpp_stopped_session_remains_connected_until_unplugged() -> None:
    """Stopping the transaction does not disconnect a vehicle still occupying the connector."""
    stopped = classify_status("Finishing", "ocpp")
    assert stopped.connected is True
    assert stopped.charging is False
    assert stopped.session == "finished"
    unplugged = classify_status("Available", "ocpp")
    assert unplugged.connected is False
    assert unplugged.charging is False
    assert unplugged.session == "disconnected"
