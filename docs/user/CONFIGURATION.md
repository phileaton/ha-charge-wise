# Configuration

Charge Wise uses selected Home Assistant entities as inputs and controls one charger per entry. You can change the
entity mappings and controller limits later through the integration's **Configure** screen.

## Entity inputs

| Input                    | Required | Expected entity/value                                                    |
| ------------------------ | -------- | ------------------------------------------------------------------------ |
| Net grid power           | Yes      | Sensor in mW, W, or kW; import positive, export negative                 |
| Measured charger power   | Yes      | Sensor in mW, W, or kW                                                   |
| Charger control          | Yes      | Switch used to start or stop charging                                    |
| Active current target    | Yes      | Writable number entity in amperes                                        |
| Safe maximum current     | Yes      | Explicit current limit that always caps requests                         |
| Hardware maximum current | No       | Read-only number entity; applies an additional, lower cap when available |
| Battery power            | No       | Power sensor; configure whether discharge is positive or negative        |
| EV connected             | No       | Binary sensor; charging is held unless it reports on                     |

The safe maximum is required even if a hardware-maximum entity is selected. If that optional entity becomes
unavailable, the configured safe maximum still applies. Multiple Charge Wise entries may share measurement sensors,
but cannot share a charger switch or active current target.

## Operating modes

- **Off** disables charging. New entries start in this mode.
- **Manual** requests the value set by the **Manual current** number entity, bounded by the configured minimum,
  maximum, and any available hardware ceiling.
- **Solar** calculates available solar headroom as `max(0, measured charger power - net grid power)`. It converts that
  budget to current using the configured single-phase voltage and never requests more than the configured limits.

The selected mode is restored after a Home Assistant restart. A restored mode is checked against current sensor values
and held through the restart cooldown before Solar can start.

## Controller options

| Option                          |  Default | Description                                                                    |
| ------------------------------- | -------: | ------------------------------------------------------------------------------ |
| Minimum operating current       |      6 A | Lowest current that may be requested                                           |
| Safe maximum current            | Required | Explicit maximum current used as a safety cap                                  |
| Charging voltage                |    240 V | Single-phase voltage for power-to-current conversion                           |
| Solar start threshold           |  1,800 W | Available solar headroom required to start charging                            |
| Low-solar confirmation          |     90 s | How long headroom may remain below minimum before charging stops               |
| Restart cooldown                |    3 min | Minimum wait after stopping or restoring a mode before Solar can restart       |
| Battery discharge threshold     |    300 W | Discharge level that starts the protection confirmation timer                  |
| Battery recovery threshold      |    150 W | Discharge must remain below this level before protection clears                |
| Battery protection confirmation |     90 s | Time discharge must exceed its threshold before protection activates           |
| Battery recovery confirmation   |     90 s | Time discharge must stay below its recovery threshold before protection clears |
| Current adjustment deadband     |      1 A | Smaller target changes are ignored                                             |

For battery protection, Charge Wise reduces the target by the ceiling of the full measured discharge divided by the
configured voltage. If the reduced target would be below the minimum operating current, charging stops. The battery
protection binary sensor is created only when a battery-power entity is configured.

## Safety and unavailable inputs

- In Solar mode, invalid or unavailable grid or charger power stops charging. A configured battery sensor that becomes
  invalid also stops Solar operation.
- If an EV-connected sensor is configured, an unavailable or disconnected state holds charging in both Manual and
  Solar modes.
- If optional battery or EV-connected sensors are not configured, the integration cannot provide those protections.
- There is no generic stale-reading timeout or handling of source-specific timestamp attributes. Charge Wise relies
  on each source integration to mark stale readings unavailable.
- Sensor recovery does not change the selected mode. Solar only resumes after its safety checks and cooldown.
- A failed target or switch command is reported as an error and triggers a best-effort stop command.

## Entities

Each entry creates:

- **Mode** select.
- **Manual current** number.
- **Controller status** sensor with the stable states Off, Waiting, Charging, Paused, and Error.
- **Available solar budget**, **Requested current**, and **Decision reason** sensors.
- **Battery protection active** binary sensor when battery power is configured.

Entity IDs are based on the charger name chosen during setup. Use the entity picker in automations and dashboards
rather than assuming an ID.

## Existing demo entries

The previous demo asked for a username and password. Those entries are not migrated. Remove the old Charge Wise entry
and add it again with the charger entities.

## Troubleshooting

### Solar remains paused

Check that the grid-power sign is import-positive/export-negative, the selected power entities report mW, W, or kW,
and any configured battery or EV-connected sensor is available and valid. The **Decision reason** sensor reports the
specific condition.

### A charger command fails

Confirm that the selected switch and current target are available, that the target accepts amperes, and that the
configured safe maximum is supported by the charger. Review Home Assistant logs and the **Controller status** and
**Decision reason** entities.
