"""Binary sensor for active battery-discharge protection."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.const import EntityCategory

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="battery_protection",
    translation_key="battery_protection",
    entity_category=EntityCategory.DIAGNOSTIC,
)


class ChargeWiseBatteryProtectionBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Report when the controller is reducing or stopping charge for battery protection."""

    entity_description = ENTITY_DESCRIPTION

    @property
    def is_on(self) -> bool | None:
        """Return the active battery-protection state."""
        return self.coordinator.data.battery_protection_active
