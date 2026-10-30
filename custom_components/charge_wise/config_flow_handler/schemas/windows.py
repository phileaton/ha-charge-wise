"""Form fields for the off-peak windows, flattened to one start, end and days field per window."""

from collections.abc import Mapping
from typing import Any

import probatio

from custom_components.charge_wise.const import CONF_OFFPEAK_WINDOWS
from custom_components.charge_wise.utils.tariff_windows import WindowDays
from homeassistant.helpers import selector

MAX_WINDOWS = 3

_DAYS_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[days.value for days in WindowDays],
        translation_key="offpeak_days",
        mode=selector.SelectSelectorMode.DROPDOWN,
    ),
)


def window_key(index: int, field: str) -> str:
    """Return the form key of one field of a window, counting windows from 1."""
    return f"offpeak_window_{index}_{field}"


def window_form_keys() -> set[str]:
    """Return every flat form key used for windows."""
    return {window_key(i, field) for i in range(1, MAX_WINDOWS + 1) for field in ("start", "end", "days")}


def windows_to_form(options: Mapping[str, Any]) -> dict[str, str]:
    """Expand stored windows into suggested form values."""
    raw = options.get(CONF_OFFPEAK_WINDOWS)
    values: dict[str, str] = {}
    if not isinstance(raw, list):
        return values
    for index, window in enumerate(raw[:MAX_WINDOWS], start=1):
        if not isinstance(window, dict):
            continue
        values[window_key(index, "start")] = str(window.get("start", ""))
        values[window_key(index, "end")] = str(window.get("end", ""))
        values[window_key(index, "days")] = str(window.get("days", WindowDays.ALL))
    return values


def add_window_fields(schema: dict[probatio.Marker, selector.Selector]) -> None:
    """Add optional fields for each window; a window is unused while its start and end are empty."""
    for index in range(1, MAX_WINDOWS + 1):
        schema[probatio.Optional(window_key(index, "start"))] = selector.TimeSelector()
        schema[probatio.Optional(window_key(index, "end"))] = selector.TimeSelector()
        schema[probatio.Optional(window_key(index, "days"), default=WindowDays.ALL.value)] = _DAYS_SELECTOR


def form_to_options(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Collapse the flat window fields into the stored window list."""
    flat_keys = window_form_keys()
    options = {key: value for key, value in user_input.items() if key not in flat_keys}
    windows: list[dict[str, str]] = []
    for index in range(1, MAX_WINDOWS + 1):
        start = user_input.get(window_key(index, "start"))
        end = user_input.get(window_key(index, "end"))
        if start and end:
            windows.append(
                {
                    "start": start[:5],
                    "end": end[:5],
                    "days": user_input.get(window_key(index, "days"), WindowDays.ALL.value),
                },
            )
    options[CONF_OFFPEAK_WINDOWS] = windows
    return options


def validate_windows(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Reject half-filled windows and windows that start and end at the same time."""
    for index in range(1, MAX_WINDOWS + 1):
        start = user_input.get(window_key(index, "start"))
        end = user_input.get(window_key(index, "end"))
        if bool(start) != bool(end):
            return {"base": "offpeak_window_incomplete"}
        if start and end and start[:5] == end[:5]:
            return {"base": "offpeak_window_empty"}
    return {}
