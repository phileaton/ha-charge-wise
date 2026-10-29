"""Config flow for selecting the Home Assistant entities Charge Wise controls."""

from typing import Any

from custom_components.charge_wise.config_flow_handler.options_flow import ChargeWiseOptionsFlow
from custom_components.charge_wise.config_flow_handler.schemas import get_configuration_schema
from custom_components.charge_wise.config_flow_handler.validators.configuration import validate_configuration
from custom_components.charge_wise.const import CONF_CHARGER_SWITCH_ENTITY, DOMAIN
from homeassistant import config_entries


class ChargeWiseConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Create a Charge Wise entry from existing Home Assistant entities."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ChargeWiseOptionsFlow:
        """Return the options flow for an entry."""
        return ChargeWiseOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Validate selected entities and create an entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_configuration(self.hass, user_input)
            if not errors:
                switch_entity = user_input[CONF_CHARGER_SWITCH_ENTITY]
                switch_state = self.hass.states.get(switch_entity)
                title = (
                    switch_state.attributes.get("friendly_name", switch_entity)
                    if switch_state is not None
                    else switch_entity
                )
                return self.async_create_entry(
                    title=title,
                    data={},
                    options=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=get_configuration_schema(),
            errors=errors,
        )


__all__ = ["ChargeWiseConfigFlowHandler"]
