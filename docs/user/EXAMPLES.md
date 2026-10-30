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
      entity_id: switch.garage_charger_off_peak_charging
mode: single
```

Charge Wise does not compare tariffs or electricity prices; the windows are fixed times you enter.

## Dashboard

An importable dashboard using standard Home Assistant cards is in [charge_wise_dashboard.yaml](./charge_wise_dashboard.yaml).
Update its sample entity IDs after adding the integration. Remove the battery-protection entity from the dashboard if
you did not configure a battery sensor.

## Related documentation

- [Configuration](./CONFIGURATION.md) describes the available safeguards and options.
- [Getting Started](./GETTING_STARTED.md) covers setup and safe initial operation.
