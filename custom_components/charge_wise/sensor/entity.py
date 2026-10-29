"""Sensor entity for charge_wise."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.typing import StateType


@dataclass(frozen=True, kw_only=True)
class ChargeWiseSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor and how to read it from coordinator data."""

    value_fn: Callable[[dict[str, Any]], StateType]


class ChargeWiseSensor(SensorEntity, ChargeWiseEntity):
    """Sensor backed by one value in the coordinator payload."""

    entity_description: ChargeWiseSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the value read from coordinator data."""
        return self.entity_description.value_fn(self.coordinator.data)
