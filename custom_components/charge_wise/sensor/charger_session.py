"""Observed session status and source evidence."""

from custom_components.charge_wise.sensor.entity import ChargeWiseSensorEntityDescription
from custom_components.charge_wise.utils.charger_status import ChargerSessionStatus
from homeassistant.components.sensor import SensorDeviceClass

ENTITY_DESCRIPTION = ChargeWiseSensorEntityDescription(
    key="charger_session",
    translation_key="charger_session",
    device_class=SensorDeviceClass.ENUM,
    options=[status.value for status in ChargerSessionStatus],
    value_fn=lambda data: data.charger_session,
    attributes_fn=lambda data: {
        "profile": data.charger_status_profile,
        "raw_status": data.charger_raw_status,
        "connection_source": data.charger_connection_source,
        "charging_source": data.charger_charging_source,
    },
)
