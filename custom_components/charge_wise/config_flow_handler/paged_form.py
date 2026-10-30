"""State shared by the multi-page setup and options flows."""

from collections.abc import Mapping
from typing import Any

import probatio

from custom_components.charge_wise.config_flow_handler.schemas import PAGE_SCHEMAS, PAGES
from custom_components.charge_wise.config_flow_handler.schemas.windows import form_to_options, windows_to_form
from custom_components.charge_wise.config_flow_handler.validators.configuration import PAGE_VALIDATORS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

BACK_KEY = "go_back"


class PagedForm:
    """Collect the values of each page and build the final options once the last page is accepted."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        stored: Mapping[str, Any] | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Start with the stored options, which fill defaults and suggested values, or with nothing."""
        self._hass = hass
        self._stored: Mapping[str, Any] = stored or {}
        self._entry_id = entry_id
        self.values: dict[str, Any] = {}

    def validate(self, page: str, user_input: dict[str, Any]) -> dict[str, str]:
        """Return the errors for one page, validated together with the pages accepted before it."""
        return PAGE_VALIDATORS[page](self._hass, {**self.values, **user_input}, current_entry_id=self._entry_id)

    def accept(self, user_input: dict[str, Any]) -> None:
        """Keep the values of a validated page."""
        self.values.update(user_input)

    @staticmethod
    def next_page(page: str) -> str | None:
        """Return the page after this one, or None after the last."""
        index = PAGES.index(page) + 1
        return PAGES[index] if index < len(PAGES) else None

    @staticmethod
    def previous_page(page: str) -> str | None:
        """Return the page before this one, or None on the first."""
        index = PAGES.index(page) - 1
        return PAGES[index] if index >= 0 else None

    def schema(self, page: str) -> probatio.Schema:
        """Build the schema of a page, with a trailing go-back toggle on every page but the first."""
        schema = PAGE_SCHEMAS[page]({**self._stored, **self.values})
        if self.previous_page(page) is None:
            return schema
        return probatio.Schema(
            {**schema.schema, probatio.Optional(BACK_KEY, default=False): selector.BooleanSelector()},
        )

    def suggested(self, schema: probatio.Schema, user_input: dict[str, Any] | None) -> dict[str, Any]:
        """Return the values to prefill, preferring what the user just typed over what is stored."""
        base = {**self._stored, **windows_to_form(self._stored), **self.values}
        if user_input is None:
            return base
        page_keys = {str(marker) for marker in schema.schema}
        return {**{k: v for k, v in base.items() if k not in page_keys}, **user_input}

    def options(self) -> dict[str, Any]:
        """Return the options to store."""
        return form_to_options(self.values)
