# Examples

These examples assume the Charge Wise entry is named **Garage Charger**. Replace the sample entity IDs with the IDs
shown in your Home Assistant entity picker.

## Automations

### Select Solar mode when the EV connects

Use the same EV-connected binary sensor selected in the Charge Wise configuration:

```yaml
alias: Use solar charging when the EV connects
triggers:
  - trigger: state
    entity_id: binary_sensor.ev_connected
    to: "on"
actions:
  - action: select.select_option
    target:
      entity_id: select.garage_charger_mode
    data:
      option: solar
mode: single
```

### Schedule a Manual charging window

This example requests 12 A in Manual mode from 01:00 to 05:00. Choose a current and schedule suitable for your
installation. This is a fixed schedule; Charge Wise does not compare tariffs or electricity prices.

```yaml
alias: Charge manually overnight
triggers:
  - trigger: time
    at: "01:00:00"
actions:
  - action: number.set_value
    target:
      entity_id: number.garage_charger_manual_current
    data:
      value: 12
  - action: select.select_option
    target:
      entity_id: select.garage_charger_mode
    data:
      option: manual
mode: single
```

Create a second automation to return the controller to Off:

```yaml
alias: Stop the overnight charging window
triggers:
  - trigger: time
    at: "05:00:00"
actions:
  - action: select.select_option
    target:
      entity_id: select.garage_charger_mode
    data:
      option: off
mode: single
```

## Dashboard

An importable dashboard using standard Home Assistant cards is in [charge_wise_dashboard.yaml](./charge_wise_dashboard.yaml).
Update its sample entity IDs after adding the integration. Remove the battery-protection entity from the dashboard if
you did not configure a battery sensor.

## Related documentation

- [Configuration](./CONFIGURATION.md) describes the available safeguards and options.
- [Getting Started](./GETTING_STARTED.md) covers setup and safe initial operation.
