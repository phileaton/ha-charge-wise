"""Warning when the EV persistently draws less current than offered."""

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass

ENTITY_DESCRIPTION = BinarySensorEntityDescription(
    key="ev_under_drawing",
    translation_key="ev_under_drawing",
    device_class=BinarySensorDeviceClass.PROBLEM,
)


class ChargeWiseEvUnderDrawingBinarySensor(BinarySensorEntity, ChargeWiseEntity):
    """Expose the confirmed current shortfall for dashboards and automations."""

    @property
    def is_on(self) -> bool | None:
        """Return unknown when the current comparison cannot be made."""
        return self.coordinator.data.ev_under_drawing
