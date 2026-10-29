"""
API package for charge_wise.

Exception hierarchy:
    ChargeWiseApiClientError (base)
    ├── ChargeWiseApiClientCommunicationError (network/timeout)
    └── ChargeWiseApiClientAuthenticationError (401/403)

The coordinator maps them onto ConfigEntryAuthFailed and UpdateFailed; nothing else
in the integration imports this package.
"""

from .client import (
    FAN_SPEEDS,
    ChargeWiseApiClient,
    ChargeWiseApiClientAuthenticationError,
    ChargeWiseApiClientCommunicationError,
    ChargeWiseApiClientError,
)

__all__ = [
    "FAN_SPEEDS",
    "ChargeWiseApiClient",
    "ChargeWiseApiClientAuthenticationError",
    "ChargeWiseApiClientCommunicationError",
    "ChargeWiseApiClientError",
]
