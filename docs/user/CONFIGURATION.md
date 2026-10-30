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

## Charging sources

Four switches control what Charge Wise does. All start off on a new entry.

- **Charging enabled** is the master switch. While it is off, nothing is charged.
- **Solar charging** calculates available solar headroom as `max(0, measured charger power - net grid power)`. It
  converts that budget to current using the configured single-phase voltage and never requests more than the
  configured limits.
- **Off-peak charging** charges from the grid at the **Off-peak current** while an off-peak window is active. It
  ignores the solar budget and battery protection, but still respects the EV-connected sensor, the current maximum
  and the failure stop.
- **Manual override** requests only the **Manual current** and ignores the Solar and off-peak sources.

Solar and off-peak can be on together. Inside a window the higher of the two requested currents wins, and Solar wins a
tie. Outside a window Solar runs as usual.

The switch states are restored after a Home Assistant restart. A restored Solar source is checked against current
sensor values and held through the restart cooldown before it can start.

## Off-peak windows

Set up to three windows in the setup or options form. Each has a start time, an end time and the days it applies to:
every day, weekdays or weekends. Leave start and end empty to skip a window. A window may cross midnight, for example
23:00 to 06:00, and its days refer to the day it starts. Start and end must differ. Seasons, holidays and rate
imports are not supported.

## EV-first charging

Optionally let the EV use power that would otherwise charge the home battery, when the solar forecast says the battery
will still reach its target by sunset. Set all four of these in the setup or options form, or none:

- **Solar forecast remaining today**: an energy sensor in Wh, kWh or MWh, such as Forecast.Solar.
- **Battery level**: a percent sensor.
- **Average house consumption**: a power sensor, excluding the charger.
- **Battery capacity (kWh)**.

**Battery target by sunset** (default 90 %) and **Forecast trust** (default 80 %) tune how cautious it is. Turn on the
**EV-first charging** switch, which also needs **Solar charging**. While the trusted forecast, less house consumption
until sunset, covers the battery's remaining need, the Solar budget also includes the power flowing into the battery
(the **EV-first active** binary sensor shows this and the decision reason becomes EV first). Otherwise, or when an
input or `sun.sun` is unavailable, Solar charging uses export only. The EV never draws from the battery itself.

## Controller options

| Option                          |  Default | Description                                                                    |
| ------------------------------- | -------: | ------------------------------------------------------------------------------ |
| Minimum operating current       |      6 A | Lowest current that may be requested                                           |
| Safe maximum current            | Required | Explicit maximum current used as a safety cap                                  |
| Charging voltage                |    240 V | Single-phase voltage for power-to-current conversion                           |
| Solar start threshold           |  1,800 W | Available solar headroom required to start charging                            |
| Low-solar confirmation          |     90 s | How long headroom may remain below minimum before charging stops               |
| Restart cooldown                |    3 min | Minimum wait after stopping or restoring Solar before it can restart           |
| Battery discharge threshold     |    300 W | Discharge level that starts the protection confirmation timer                  |
| Battery recovery threshold      |    150 W | Discharge must remain below this level before protection clears                |
| Battery protection confirmation |     90 s | Time discharge must exceed its threshold before protection activates           |
| Battery recovery confirmation   |     90 s | Time discharge must stay below its recovery threshold before protection clears |
| Current adjustment deadband     |      1 A | Smaller target changes are ignored                                             |

For battery protection, Charge Wise reduces the target by the ceiling of the full measured discharge divided by the
configured voltage. If the reduced target would be below the minimum operating current, charging stops. The battery
protection binary sensor is created only when a battery-power entity is configured.

## Safety and unavailable inputs

- For the Solar source, invalid or unavailable grid or charger power stops charging. A configured battery sensor that becomes
  invalid also stops Solar operation.
- If an EV-connected sensor is configured, an unavailable or disconnected state holds charging for every source.
- If optional battery or EV-connected sensors are not configured, the integration cannot provide those protections.
- There is no generic stale-reading timeout or handling of source-specific timestamp attributes. Charge Wise relies
  on each source integration to mark stale readings unavailable.
- Sensor recovery does not change the switches. Solar only resumes after its safety checks and cooldown.
- A failed target or switch command is reported as an error and triggers a best-effort stop command.

## Entities

Each entry creates:

- **Charging enabled**, **Solar charging**, **Off-peak charging**, **Manual override** and **EV-first charging** switches.
- **Manual current** and **Off-peak current** numbers.
- **Controller status** sensor with the stable states Off, Waiting, Charging, Paused, and Error.
- **Available solar budget**, **Requested current**, and **Decision reason** sensors.
- **Next off-peak window** timestamp sensor.
- **Off-peak active** and **EV-first active** binary sensors.
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
