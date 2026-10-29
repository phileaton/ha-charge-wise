# Getting Started

Charge Wise adjusts one EV charger's current target using entities that already exist in Home Assistant. It does not
connect to a charger vendor API.

## Before setup

Have these Home Assistant entities available:

- A net grid-power sensor in mW, W, or kW. Import must be positive and export negative.
- A measured charger-power sensor in mW, W, or kW.
- The charger's on/off switch.
- A writable number entity for the active charging-current target, in amperes.
- A safe maximum current for this charger. You must enter this value even when you select a hardware-maximum entity.

Optional inputs:

- A battery-power sensor. Its sign convention is configurable; positive discharge is the default.
- A binary sensor that is on when an EV is connected. If selected, Charge Wise holds charging unless it reports the EV
  connected.
- A read-only number entity for the charger's hardware maximum current. Charge Wise applies the lower of this value
  and the configured maximum; if the entity is unavailable, the configured maximum remains in force.

Without a battery sensor, battery-discharge protection is disabled. Without an EV-connected sensor, Charge Wise cannot
detect unplugging.

## Install

Install Charge Wise through HACS as a custom integration, or copy `custom_components/charge_wise` into the
`custom_components` directory in your Home Assistant configuration and restart Home Assistant. Home Assistant
2026.10.0 or newer is required.

## Add the integration

1. Open Home Assistant's integration setup flow and find **Charge Wise**. It is classified as a calculated helper,
   not a physical device.
2. Select **Charge Wise**.
3. Select the grid-power sensor, charger-power sensor, charger switch, and writable current target.
4. Enter a safe maximum current and review the operating limits and Solar defaults.
5. Add the optional battery and EV-connected sensors if you want those protections.
6. Submit the form. The new entry starts in **Off** mode.

The setup form validates selected entity domains, available power units, safe current limits, and duplicate charger
controls. Multiple entries may share measurement sensors, but not the same charger switch or active current target.

## Start carefully

1. Confirm the selected current-target number controls the intended charger and is measured in amperes.
2. Confirm import is positive and export is negative on the grid-power sensor.
3. Keep the mode **Off** while checking the current and hardware limits.
4. Use **Manual** to request a controlled current, or **Solar** to start only when the configured solar threshold is
   met.

See [Configuration](./CONFIGURATION.md) for all thresholds and controller behavior, and [Examples](./EXAMPLES.md) for
automations and an importable dashboard.
