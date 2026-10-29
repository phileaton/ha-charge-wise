"""Data update coordinator for charge_wise."""

from typing import TYPE_CHECKING, Any

from custom_components.charge_wise.api import ChargeWiseApiClientAuthenticationError, ChargeWiseApiClientError
from custom_components.charge_wise.const import DOMAIN
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

if TYPE_CHECKING:
    from custom_components.charge_wise.data import ChargeWiseConfigEntry


class ChargeWiseDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the device state once per interval and hand it to every entity."""

    config_entry: ChargeWiseConfigEntry

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Fetch the current device state.

        Returns:
            The payload entities read by key.

        Raises:
            ConfigEntryAuthFailed: If the credentials were rejected; triggers reauth.
            UpdateFailed: If the fetch failed for any other reason.

        """
        try:
            return await self.config_entry.runtime_data.client.async_get_data()
        except ChargeWiseApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="authentication_failed",
            ) from exception
        except ChargeWiseApiClientError as exception:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
            ) from exception
