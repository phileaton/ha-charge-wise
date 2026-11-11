"""Manage an ordered collection of display-only vehicles in integration options."""

from typing import Any
from uuid import uuid4

import probatio

from custom_components.charge_wise.config_flow_handler.schemas.vehicles import vehicle_schema
from custom_components.charge_wise.config_flow_handler.validators.vehicles import validate_vehicle
from custom_components.charge_wise.const import CONF_VEHICLES
from homeassistant import config_entries
from homeassistant.helpers import selector


class VehicleOptionsFlow(config_entries.OptionsFlow):
    """Stage vehicle edits until the user explicitly saves them."""

    _vehicles: list[dict[str, Any]]
    _vehicle_id: str | None = None

    def _vehicle_list(self) -> list[dict[str, Any]]:
        if not hasattr(self, "_vehicles"):
            self._vehicles = [dict(vehicle) for vehicle in self.config_entry.options.get(CONF_VEHICLES, [])]
        return self._vehicles

    async def async_step_vehicles(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Offer vehicle management and an explicit save action."""
        vehicles = self._vehicle_list()
        actions = ["vehicle_add"]
        if vehicles:
            actions.extend(("vehicle_edit", "vehicle_remove"))
        actions.extend(("vehicle_save", "init"))
        return self.async_show_menu(step_id="vehicles", menu_options=actions)

    async def async_step_vehicle_add(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Add a named vehicle with existing source readings."""
        self._vehicle_id = None
        return await self._vehicle_form("vehicle_add", user_input)

    async def async_step_vehicle_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select the vehicle to edit."""
        if user_input is not None:
            self._vehicle_id = user_input["vehicle_id"]
            return await self.async_step_vehicle_details()
        return self._select_vehicle("vehicle_edit")

    async def async_step_vehicle_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Update the selected vehicle, including clearing optional readings."""
        return await self._vehicle_form("vehicle_details", user_input)

    async def async_step_vehicle_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Remove the selected vehicle from the staged list."""
        if user_input is not None:
            self._vehicles = [v for v in self._vehicle_list() if v["id"] != user_input["vehicle_id"]]
            return await self.async_step_vehicles()
        return self._select_vehicle("vehicle_remove")

    async def async_step_vehicle_save(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Save vehicle settings without changing charger options."""
        return self.async_create_entry(
            title="", data={**self.config_entry.options, CONF_VEHICLES: self._vehicle_list()}
        )

    def _select_vehicle(self, step: str) -> config_entries.ConfigFlowResult:
        choices: list[selector.SelectOptionDict] = [
            {"value": v["id"], "label": v["name"]} for v in self._vehicle_list()
        ]
        if not choices:
            return self.async_show_menu(step_id="vehicles", menu_options=["vehicle_add", "vehicle_save", "init"])
        return self.async_show_form(
            step_id=step,
            data_schema=probatio.Schema(
                {
                    probatio.Required("vehicle_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=choices)
                    )
                }
            ),
        )

    async def _vehicle_form(self, step: str, user_input: dict[str, Any] | None) -> config_entries.ConfigFlowResult:
        vehicles = self._vehicle_list()
        existing = next((v for v in vehicles if v["id"] == self._vehicle_id), {})
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = validate_vehicle(self.hass, user_input)
            if not errors:
                vehicle = {key: value for key, value in user_input.items() if value}
                vehicle["name"] = vehicle["name"].strip()
                vehicle["id"] = self._vehicle_id or uuid4().hex
                if existing:
                    vehicles[vehicles.index(existing)] = vehicle
                else:
                    vehicles.append(vehicle)
                return await self.async_step_vehicles()
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(
                vehicle_schema(), user_input if user_input is not None else existing
            ),
            errors=errors,
        )
