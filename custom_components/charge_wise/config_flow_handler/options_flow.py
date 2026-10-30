"""Options flow for entity mappings and charging limits."""

from typing import Any

from custom_components.charge_wise.config_flow_handler.paged_form import PagedForm
from homeassistant import config_entries


class ChargeWiseOptionsFlow(config_entries.OptionsFlow):
    """Update entity mappings and controller thresholds, one page at a time."""

    _form: PagedForm

    def _paged_form(self) -> PagedForm:
        if not hasattr(self, "_form"):
            self._form = PagedForm(
                self.hass,
                stored=self.config_entry.options,
                entry_id=self.config_entry.entry_id,
            )
        return self._form

    async def _async_page(self, page: str, user_input: dict[str, Any] | None) -> config_entries.ConfigFlowResult:
        form = self._paged_form()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = form.validate(page, user_input)
            if not errors:
                form.accept(user_input)
                next_page = form.next_page(page)
                if next_page is None:
                    return self.async_create_entry(title="", data=form.options())
                return await getattr(self, f"async_step_{next_page}")()

        schema = form.schema(page)
        return self.async_show_form(
            step_id="init" if page == "charger" else page,
            data_schema=self.add_suggested_values_to_schema(schema, form.suggested(schema, user_input)),
            errors=errors,
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Choose the charger entities and current limits."""
        return await self._async_page("charger", user_input)

    async def async_step_solar(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Set the Solar start and stop timing."""
        return await self._async_page("solar", user_input)

    async def async_step_battery(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Set battery discharge protection."""
        return await self._async_page("battery", user_input)

    async def async_step_forecast(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Set the forecast inputs for EV-first charging."""
        return await self._async_page("forecast", user_input)

    async def async_step_offpeak(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Set the off-peak windows and save."""
        return await self._async_page("offpeak", user_input)


__all__ = ["ChargeWiseOptionsFlow"]
