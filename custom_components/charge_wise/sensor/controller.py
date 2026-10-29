"""Controller status, decision reason, and calculated charging measurements."""

from custom_components.charge_wise.sensor.entity import ChargeWiseSensorEntityDescription
from custom_components.charge_wise.utils.charging_controller import ChargeWiseReason, ControllerStatus
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfPower

ENTITY_DESCRIPTIONS: tuple[ChargeWiseSensorEntityDescription, ...] = (
    ChargeWiseSensorEntityDescription(
        key="controller_status",
        translation_key="controller_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in ControllerStatus],
        value_fn=lambda data: data.status.value,
    ),
    ChargeWiseSensorEntityDescription(
        key="available_solar_budget",
        translation_key="available_solar_budget",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: data.available_solar_w,
    ),
    ChargeWiseSensorEntityDescription(
        key="requested_current",
        translation_key="requested_current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value_fn=lambda data: data.requested_current_a,
    ),
    ChargeWiseSensorEntityDescription(
        key="decision_reason",
        translation_key="decision_reason",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=[reason.value for reason in ChargeWiseReason],
        value_fn=lambda data: data.reason.value,
    ),
)


__all__ = ["ENTITY_DESCRIPTIONS"]
