"""Metadata and initial state of the no-power diagnostic."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.charge_wise.const import DOMAIN
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

pytestmark = pytest.mark.integration


async def test_charging_not_detected_is_a_diagnostic_problem(
    hass: HomeAssistant, init_integration: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    """Create an enabled diagnostic entity on the controller device without a false alarm."""
    entity_id = entity_registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{init_integration.entry_id}_charging_not_detected"
    )
    assert entity_id is not None
    registered = entity_registry.async_get(entity_id)
    assert registered is not None
    assert registered.entity_category is EntityCategory.DIAGNOSTIC
    assert registered.disabled_by is None
    assert registered.device_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"
    assert state.attributes["device_class"] == "problem"
