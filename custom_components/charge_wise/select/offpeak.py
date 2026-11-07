"""Select recurring or one-time off-peak charging."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription

ENTITY_DESCRIPTIONS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(key="offpeak_mode", translation_key="offpeak_mode", options=["off", "on", "on_once"]),
)


class ChargeWiseOffpeakSelect(SelectEntity, ChargeWiseEntity):
    """Choose whether off-peak charging repeats or stops after one period."""

    @property
    def current_option(self) -> str:
        """Return the mode published by the coordinator."""
        return self.coordinator.data.offpeak_mode

    async def async_select_option(self, option: str) -> None:
        """Set the charging mode and publish the resulting controller decision."""
        await self.coordinator.async_set_offpeak_mode(option)
