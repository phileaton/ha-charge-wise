"""Binary sensor for EV-first charging sharing the battery's charging power."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="ev_first_active",
    translation_key="ev_first_active",
)


class ChargeWiseEvFirstActiveBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Report when the forecast lets the EV use power that would charge the battery."""

    entity_description = ENTITY_DESCRIPTION

    @property
    def is_on(self) -> bool:
        """Return whether the EV-first boost is currently applied."""
        return self.coordinator.data.ev_first_active
