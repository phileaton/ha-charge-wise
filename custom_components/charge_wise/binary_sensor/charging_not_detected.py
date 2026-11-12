"""Diagnostic warning for requested charging that produces no measured power."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="charging_not_detected",
    translation_key="charging_not_detected",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


class ChargeWiseChargingNotDetectedBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Expose the confirmed no-power warning without changing charger control."""

    entity_description = ENTITY_DESCRIPTION

    @property
    def is_on(self) -> bool:
        """Return whether requested charging has failed to produce measured activity."""
        return self.coordinator.data.charging_not_detected
