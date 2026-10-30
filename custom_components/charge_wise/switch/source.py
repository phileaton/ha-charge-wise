"""Switches that enable charging and select its sources."""

from dataclasses import dataclass

from custom_components.charge_wise.coordinator.base import SwitchKey
from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_ON
from homeassistant.helpers.restore_state import RestoreEntity


@dataclass(frozen=True, kw_only=True)
class ChargeWiseSwitchEntityDescription(SwitchEntityDescription):
    """Describe which coordinator switch an entity controls."""

    switch_key: SwitchKey


ENTITY_DESCRIPTIONS: tuple[ChargeWiseSwitchEntityDescription, ...] = (
    ChargeWiseSwitchEntityDescription(key="enabled", translation_key="enabled", switch_key="enabled"),
    ChargeWiseSwitchEntityDescription(key="solar_enabled", translation_key="solar_enabled", switch_key="solar_enabled"),
    ChargeWiseSwitchEntityDescription(
        key="offpeak_enabled",
        translation_key="offpeak_enabled",
        switch_key="offpeak_enabled",
    ),
    ChargeWiseSwitchEntityDescription(
        key="manual_override",
        translation_key="manual_override",
        switch_key="manual_override",
    ),
)


class ChargeWiseSourceSwitch(SwitchEntity, RestoreEntity, ChargeWiseEntity):
    """Turn charging or one charging source on or off."""

    entity_description: ChargeWiseSwitchEntityDescription

    @property
    def is_on(self) -> bool:
        """Return the coordinator state for this switch."""
        return self.coordinator.switches[self.entity_description.switch_key]

    async def async_added_to_hass(self) -> None:
        """Restore the prior state but wait through the safety cooldown before charging."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is None or last_state.state != STATE_ON:
            return
        await self.coordinator.async_set_switch(self.entity_description.switch_key, True, restoring=True)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the switch on."""
        await self.coordinator.async_set_switch(self.entity_description.switch_key, True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the switch off."""
        await self.coordinator.async_set_switch(self.entity_description.switch_key, False)
