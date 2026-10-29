"""
Entity package for charge_wise.

Architecture:
    All platform entities inherit from (PlatformEntity, ChargeWiseEntity).
    MRO order matters — platform-specific class first, then the integration base.
    Entities read data from coordinator.data and NEVER call the API client directly.
    Unique IDs follow the pattern: {entry_id}_{description.key}

See entity/base.py for the ChargeWiseEntity base class.
"""

from .base import ChargeWiseEntity

__all__ = ["ChargeWiseEntity"]
