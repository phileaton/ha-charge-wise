# Charge Wise

Charge Wise is a Home Assistant custom integration for controlling one EV charger from existing Home Assistant
entities. It calculates charging decisions locally; it does not connect to a charger vendor API.

## What it does

- Charges from surplus solar, in configurable off-peak time windows, or both, with a manual override.
- Adjusts the current target from signed grid power and measured charger power.
- Applies configurable current limits, Solar hysteresis, cooldowns, and optional battery-discharge protection.
- Can hold charging until an optional EV-connected sensor reports a connected vehicle.
- Supports multiple independent charger entries.

The integration starts with every switch off. Configure the entities and safe current limits before turning on charging.
If battery or EV-connected sensors are omitted, the corresponding protection is unavailable.

## Requirements

- Home Assistant 2026.10.0 or newer.
- A net grid-power sensor that reports import as positive and export as negative.
- A measured charger-power sensor, a charger switch, and a writable number entity for the current target.
- An explicit safe maximum current, even if a read-only hardware-limit entity is selected.

Power sensor units may be mW, W, or kW. The writable current target must use amperes.

## Installation

Install through HACS using this repository as a custom integration, or copy `custom_components/charge_wise` into the
Home Assistant `custom_components` directory and restart Home Assistant. Then add **Charge Wise** through Home
Assistant's integration setup flow. Charge Wise is a calculated helper, not a physical device.

See [Getting Started](docs/user/GETTING_STARTED.md) for setup and safety details, [Configuration](docs/user/CONFIGURATION.md)
for all options, and [Examples](docs/user/EXAMPLES.md) for automations and dashboards.

## Development

This repository uses the development and validation scripts in `script/`. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [AI_POLICY.md](AI_POLICY.md) before contributing.
