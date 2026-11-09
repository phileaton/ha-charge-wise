"""Select recurring EV-first sharing or sharing for today only."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription

ENTITY_DESCRIPTIONS: tuple[SelectEntityDescription, ...] = (
    SelectEntityDescription(key="ev_first_mode", translation_key="ev_first_mode", options=["off", "on", "on_once"]),
)


class ChargeWiseEvFirstSelect(SelectEntity, ChargeWiseEntity):
    """Choose whether EV-first sharing repeats or stops at today's sunset."""

    @property
    def current_option(self) -> str:
        """Return the selected mode from the coordinator."""
        return self.coordinator.data.ev_first_mode

    async def async_select_option(self, option: str) -> None:
        """Apply and persist the selected EV-first mode."""
        await self.coordinator.async_set_ev_first_mode(option)
