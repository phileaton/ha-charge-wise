"""Operating mode select."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from custom_components.charge_wise.utils.charging_controller import ChargeWiseMode
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.helpers.restore_state import RestoreEntity

ENTITY_DESCRIPTION = SelectEntityDescription(
    key="mode",
    translation_key="mode",
    options=[mode.value for mode in ChargeWiseMode],
)


class ChargeWiseModeSelect(SelectEntity, RestoreEntity, ChargeWiseEntity):
    """Select Off, Manual, or Solar operation."""

    entity_description = ENTITY_DESCRIPTION

    @property
    def current_option(self) -> str:
        """Return the active mode."""
        return self.coordinator.data.mode.value

    async def async_added_to_hass(self) -> None:
        """Restore the prior mode and revalidate before allowing charging."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is None:
            return
        if ENTITY_DESCRIPTION.options is None or last_state.state not in ENTITY_DESCRIPTION.options:
            return
        await self.coordinator.async_restore_mode(ChargeWiseMode(last_state.state))

    async def async_select_option(self, option: str) -> None:
        """Apply the selected operating mode."""
        await self.coordinator.async_set_mode(ChargeWiseMode(option))
