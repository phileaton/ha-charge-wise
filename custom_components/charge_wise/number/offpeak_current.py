"""Off-peak charging-current control."""

from custom_components.charge_wise.const import DOMAIN
from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.restore_state import RestoreEntity

ENTITY_DESCRIPTION = NumberEntityDescription(
    key="offpeak_current",
    translation_key="offpeak_current",
    device_class=NumberDeviceClass.CURRENT,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    native_min_value=1,
    native_max_value=80,
    native_step=1,
    mode=NumberMode.BOX,
)


class ChargeWiseOffpeakCurrentNumber(NumberEntity, RestoreEntity, ChargeWiseEntity):
    """Set the grid charging current used inside off-peak windows."""

    entity_description = ENTITY_DESCRIPTION

    @property
    def native_value(self) -> float:
        """Return the saved off-peak current target."""
        return self.coordinator.data.offpeak_current_a

    @property
    def native_min_value(self) -> float:
        """Return the configured minimum operating current."""
        return float(self.coordinator.controller.config.minimum_current_a)

    @property
    def native_max_value(self) -> float:
        """Return the configured maximum current."""
        return float(self.coordinator.controller.config.maximum_current_a)

    async def async_added_to_hass(self) -> None:
        """Restore the prior target after Home Assistant restarts."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is None:
            return
        try:
            current_a = float(last_state.state)
        except ValueError:
            return
        if self.native_min_value <= current_a <= self.native_max_value:
            await self.coordinator.async_set_offpeak_current(current_a)

    async def async_set_native_value(self, value: float) -> None:
        """Store the requested current and apply it while an off-peak window is active."""
        if not self.native_min_value <= value <= self.native_max_value:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_manual_current",
                translation_placeholders={
                    "minimum": str(self.native_min_value),
                    "maximum": str(self.native_max_value),
                },
            )
        await self.coordinator.async_set_offpeak_current(value)
