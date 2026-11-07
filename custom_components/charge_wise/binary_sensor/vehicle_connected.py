"""Observed vehicle connected state from charger evidence."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="vehicle_connected",
    translation_key="vehicle_connected",
    device_class=BinarySensorDeviceClass.PLUG,
)


class ChargeWiseVehicleConnectedBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Expose observed vehicle connected state independently of controller commands."""

    @property
    def is_on(self) -> bool | None:
        """Return the observed value, or unknown when evidence is missing."""
        return self.coordinator.data.vehicle_connected
