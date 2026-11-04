"""Shared coordinator-backed sensor entity."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from custom_components.charge_wise.coordinator.data import ChargeWiseSnapshot
from custom_components.charge_wise.entity import ChargeWiseEntity
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.typing import StateType


@dataclass(frozen=True, kw_only=True)
class ChargeWiseSensorEntityDescription(SensorEntityDescription):
    """Describe how a sensor reads the coordinator snapshot."""

    value_fn: Callable[[ChargeWiseSnapshot], StateType | datetime]
    attributes_fn: Callable[[ChargeWiseSnapshot], Mapping[str, StateType]] | None = None


class ChargeWiseSensor(SensorEntity, ChargeWiseEntity):
    """Expose one value from the coordinator snapshot."""

    entity_description: ChargeWiseSensorEntityDescription

    @property
    def native_value(self) -> StateType | datetime:
        """Return the snapshot value selected by the entity description."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> Mapping[str, StateType] | None:
        """Return the extra attributes selected by the entity description."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
