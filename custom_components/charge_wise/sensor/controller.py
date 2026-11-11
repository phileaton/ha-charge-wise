"""Controller status, decision reason, and calculated charging measurements."""

from custom_components.charge_wise.sensor.entity import ChargeWiseSensorEntityDescription
from custom_components.charge_wise.utils.charging_controller import ChargeWiseReason, ControllerStatus
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricCurrent, UnitOfEnergy, UnitOfPower

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
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        value_fn=lambda data: data.available_solar_w,
    ),
    ChargeWiseSensorEntityDescription(
        key="average_house_load",
        translation_key="average_house_load",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        value_fn=lambda data: data.average_house_load_w,
    ),
    ChargeWiseSensorEntityDescription(
        key="house_load",
        translation_key="house_load",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        value_fn=lambda data: data.house_load_w,
    ),
    ChargeWiseSensorEntityDescription(
        key="battery_need",
        translation_key="battery_need",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda data: data.battery_need_kwh,
    ),
    ChargeWiseSensorEntityDescription(
        key="forecast_surplus",
        translation_key="forecast_surplus",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda data: data.forecast_surplus_kwh,
    ),
    ChargeWiseSensorEntityDescription(
        key="forecast_accuracy",
        translation_key="forecast_accuracy",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda data: data.forecast_accuracy_percent,
        attributes_fn=lambda data: {
            "actual_vs_forecast": f"{data.forecast_accuracy_actual_kwh or 0:.1f} of {data.forecast_accuracy_forecast_kwh or 0:.1f} kWh"
        },
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
        key="restart_cooldown_end",
        translation_key="restart_cooldown_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.restart_cooldown_end,
    ),
    ChargeWiseSensorEntityDescription(
        key="next_offpeak_window",
        translation_key="next_offpeak_window",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.next_offpeak_start,
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
