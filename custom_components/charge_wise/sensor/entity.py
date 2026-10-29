"""Shared coordinator-backed sensor entity."""

from collections.abc import Callable
from dataclasses import dataclass

from custom_components.charge_wise.coordinator.data import ChargeWiseSnapshot
from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.typing import StateType


@dataclass(frozen=True, kw_only=True)
class ChargeWiseSensorEntityDescription(SensorEntityDescription):
    """Describe how a sensor reads the coordinator snapshot."""

    value_fn: Callable[[ChargeWiseSnapshot], StateType]


class ChargeWiseSensor(SensorEntity, ChargeWiseEntity):
    """Expose one value from the coordinator snapshot."""

    entity_description: ChargeWiseSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the snapshot value selected by the entity description."""
        return self.entity_description.value_fn(self.coordinator.data)
