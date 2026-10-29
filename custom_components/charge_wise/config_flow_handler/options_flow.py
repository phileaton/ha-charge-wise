"""Options flow for entity mappings and charging limits."""

from typing import Any

from custom_components.charge_wise.config_flow_handler.schemas import get_configuration_schema
from custom_components.charge_wise.config_flow_handler.validators.configuration import validate_configuration
from homeassistant import config_entries


class ChargeWiseOptionsFlow(config_entries.OptionsFlow):
    """Update entity mappings and controller thresholds."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Validate and store the updated options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_configuration(
                self.hass,
                user_input,
                current_entry_id=self.config_entry.entry_id,
            )
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        schema = self.add_suggested_values_to_schema(
            get_configuration_schema(self.config_entry.options),
            self.config_entry.options,
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )


__all__ = ["ChargeWiseOptionsFlow"]
