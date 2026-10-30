"""Config flow for selecting the Home Assistant entities Charge Wise controls."""

from typing import Any

from custom_components.charge_wise.config_flow_handler.options_flow import ChargeWiseOptionsFlow
from custom_components.charge_wise.config_flow_handler.paged_form import BACK_KEY, PagedForm
from custom_components.charge_wise.const import CONF_CHARGER_SWITCH_ENTITY, DOMAIN
from homeassistant import config_entries


class ChargeWiseConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a Charge Wise entry from existing Home Assistant entities, one page at a time."""

    VERSION = 1

    _form: PagedForm

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ChargeWiseOptionsFlow:
        """Return the options flow for an entry."""
        return ChargeWiseOptionsFlow()

    def _paged_form(self) -> PagedForm:
        if not hasattr(self, "_form"):
            self._form = PagedForm(self.hass)
        return self._form

    async def _async_page(self, page: str, user_input: dict[str, Any] | None) -> config_entries.ConfigFlowResult:
        form = self._paged_form()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = dict(user_input)
            go_back = user_input.pop(BACK_KEY, False)
            previous_page = form.previous_page(page)
            if go_back and previous_page is not None:
                form.accept(user_input)
                return await self._async_page(previous_page, None)
            errors = form.validate(page, user_input)
            if not errors:
                form.accept(user_input)
                next_page = form.next_page(page)
                if next_page is None:
                    return self._create_entry(form)
                return await self._async_page(next_page, None)

        schema = form.schema(page)
        return self.async_show_form(
            step_id="user" if page == "charger" else page,
            data_schema=self.add_suggested_values_to_schema(schema, form.suggested(schema, user_input)),
            errors=errors,
            last_step=form.next_page(page) is None,
        )

    def _create_entry(self, form: PagedForm) -> config_entries.ConfigFlowResult:
        switch_entity = form.values[CONF_CHARGER_SWITCH_ENTITY]
        switch_state = self.hass.states.get(switch_entity)
        title = (
            switch_state.attributes.get("friendly_name", switch_entity) if switch_state is not None else switch_entity
        )
        return self.async_create_entry(title=title, data={}, options=form.options())

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
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
        """Set the off-peak windows and create the entry."""
        return await self._async_page("offpeak", user_input)


__all__ = ["ChargeWiseConfigFlowHandler"]
