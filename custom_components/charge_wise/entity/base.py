"""Base entity for Charge Wise platforms."""

from custom_components.charge_wise.coordinator import ChargeWiseDataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity


class ChargeWiseEntity(CoordinatorEntity[ChargeWiseDataUpdateCoordinator]):
    """Provide shared coordinator access and stable entry-scoped unique IDs."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargeWiseDataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the entity from its description."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(coordinator.entry.domain, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="Charge Wise",
            model="Charging controller",
        )
