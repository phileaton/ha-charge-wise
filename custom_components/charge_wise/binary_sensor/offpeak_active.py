"""Binary sensor for an active off-peak charging window."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="offpeak_active",
    translation_key="offpeak_active",
)


class ChargeWiseOffpeakActiveBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Report when off-peak charging is enabled and inside a window."""

    entity_description = ENTITY_DESCRIPTION

    @property
    def is_on(self) -> bool:
        """Return whether an off-peak window is currently charging-eligible."""
        return self.coordinator.data.offpeak_active
