"""Observed vehicle charging state from charger evidence."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="vehicle_charging",
    translation_key="vehicle_charging",
    device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
)


class ChargeWiseVehicleChargingBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Expose observed vehicle charging state independently of controller commands."""

    @property
    def is_on(self) -> bool | None:
        """Return the observed value, or unknown when evidence is missing."""
        return self.coordinator.data.vehicle_charging
