# Examples

These examples assume the Charge Wise entry is named **Garage Charger**. Replace the sample entity IDs with the IDs
shown in your Home Assistant entity picker.

## Automations

### Turn on Solar charging when the EV connects

Use the same EV-connected binary sensor selected in the Charge Wise configuration:

```yaml
alias: Use solar charging when the EV connects
triggers:
  - trigger: state
    entity_id: binary_sensor.ev_connected
    to: "on"
actions:
  - action: switch.turn_on
    target:
      entity_id:
        - switch.garage_charger_charging_enabled
        - switch.garage_charger_solar_charging
mode: single
```

### Charge overnight on a cheap tariff

Configure an off-peak window such as 23:00 to 06:00 in the options form, set **Off-peak current** and turn on
**Off-peak charging**. Charge Wise starts and stops at the window edges without an automation. With **Solar charging**
also on, Solar continues outside the window.

```yaml
alias: Enable off-peak charging
triggers:
  - trigger: homeassistant
    event: start
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.garage_charger_charging_enabled
  - action: select.select_option
    target:
      entity_id: select.garage_charger_off_peak_charging
    data:
      option: "on"
mode: single
```

Charge Wise does not compare tariffs or electricity prices; the windows are fixed times you enter.

## Dashboard

The last setup page has a **Create a dashboard** option, on by default. It adds a sidebar dashboard named after your
charger, built from your real entities. Its solar forecast chart uses the community
[ApexCharts Card](https://github.com/RomRider/apexcharts-card); install it through HACS and add its Lovelace resource
if you configure both a forecast sensor and solar production. For the forecast curve, enable **Half-hourly detail** in
the Solcast Solar integration. Charge Wise refreshes the dashboard each time the integration loads, so edits you make
to it are overwritten; copy it into a dashboard of your own to customise it.
Untick the option in the integration's options, or delete the integration, to remove the dashboard.

Entries set up before this option existed do not get a dashboard until you tick it in their options.

If you prefer to build your own, an importable dashboard is in [charge_wise_dashboard.yaml](./charge_wise_dashboard.yaml).
Update its sample entity IDs after adding the integration. Remove the battery-protection entity if you did not
configure a battery sensor, and the EV-first and average house consumption entities if you did not configure the
forecast page.

## Related documentation

- [Configuration](./CONFIGURATION.md) describes the available safeguards and options.
- [Getting Started](./GETTING_STARTED.md) covers setup and safe initial operation.
