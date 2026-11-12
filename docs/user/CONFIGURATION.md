# Configuration

Charge Wise uses selected Home Assistant entities as inputs and controls one charger per entry. You can change the
entity mappings and controller limits later through the integration's **Configure** screen.

**Configure** first offers **Charger** settings or **Vehicles**. Setup and Charger settings walk five pages: **Charger** (entities and current limits), **Solar charging**,
**Battery protection**, **EV-first charging** and **Off-peak windows** (with the dashboard option). The last page saves everything; nothing is
stored if you close the dialog earlier. Pages with optional features can be submitted as they are. Home Assistant
forms have no Back button, so pages 2 to 5 end with a **Go back to the previous page** toggle: tick it and select
**Next** (or **Submit** on the last page) to return without validating the page. Its values are kept.

## Entity inputs

| Input                       | Required | Expected entity/value                                                    |
| --------------------------- | -------- | ------------------------------------------------------------------------ |
| Net grid power              | Yes      | Sensor in mW, W, or kW; import positive, export negative                 |
| Measured charger power      | Yes      | Sensor in mW, W, or kW                                                   |
| Charger control             | Yes      | Switch used to start or stop charging                                    |
| Active current target       | Yes      | Writable number entity in amperes                                        |
| Safe maximum current        | Yes      | Current limit for Charge Wise-controlled charging                        |
| Hardware maximum current    | No       | Read-only number entity; applies an additional, lower cap when available |
| Battery power               | No       | Power sensor; configure whether discharge is positive or negative        |
| Charger status / connection | No       | Binary connection sensor, or status sensor with a profile                |

The safe maximum is required even if a hardware-maximum entity is selected. If that optional entity becomes
unavailable, the configured safe maximum still applies. Multiple Charge Wise entries may share measurement sensors,
but cannot share a charger switch, active current target, or native solar-mode control.

The writable current target must report amperes, expose minimum, maximum and step attributes, cover your entire
configured current range, and accept every whole-amp value in that range. A target limited to 16 A cannot be used
with a configured 32 A maximum. A 0.1 A step is supported; a 2 A step cannot represent every requested current.

## Vehicle dashboard cards

Open **Configure → Vehicles** to add, edit or remove vehicle cards, then choose **Save vehicles** to apply the list.
Closing the dialog without saving keeps the previous list. Each vehicle needs a display name and battery percentage
sensor. Optional readings include a charge target, connected and charging flags, charging power, range and native
time remaining. Clear an optional selection to hide it. Vehicle settings do not choose which car is charging or
change the charging controller's decisions.

A charge target supplied by a writable number entity gets dashboard adjustment buttons. These directly change that
vehicle's existing target control. A sensor target remains read-only.

For vehicles without a valid native duration, select that vehicle's charging-power sensor and enter its usable
battery capacity (0.1–1000 kWh). Charge Wise estimates time to the selected charge target, or 100% if no target is
configured. It requires positive power and valid battery/target percentages; any configured connected and charging
flags must be on. Missing inputs show Unavailable. The estimate assumes a constant rate and excludes charging losses
and tapering; it does not schedule charging or guarantee a completion time. Valid native durations take precedence.

## Charger status and connection

Select the charger status sensor and its profile on the Charger page. Automatic recognizes sensors supplied by the
OCPP and Wallbox integrations; other integrations need an explicit profile or Custom mappings. For your own sensor,
enter each reported value in exactly one custom group: disconnected, idle (connected), charging, paused, finished or
fault. Matching ignores surrounding whitespace and case. Leave uncertain statuses unmapped.

Use this single field for either type of source. A binary sensor reports connection through on/off; it does not
provide session status, and the profile is ignored. A string status sensor uses the selected profile for both
connection and session information. Older saved connection selections remain readable until the options are saved;
if both old fields were configured, the charger status selection is used. Saving Configure stores the single source.

OCPP Available means disconnected and Preparing means connected. Wallbox Locked means disconnected, while
Locked, car connected means connected. Unsupported values and fault or unavailable statuses do not establish a
connection. This replaces the previous assumption that any string except Available meant connected; existing
installations using arbitrary status strings must configure a profile or select a binary connection sensor.

Vehicle charging uses measured power: at least 100 W turns it on, at most 50 W turns it off, and values between
retain the previous valid observation. Missing or invalid power resets it to unknown. Zero power never implies an
unplugged vehicle or completed session. Status supplies charging activity only when no power sensor is configured;
measured charger power remains required by setup and solar control.

Charger session describes what the status sensor reports, independently of measured activity. Finished means an
explicitly ended session, not a full battery. OCPP Finishing reports session completion while keeping the vehicle connected;
Available reports disconnection. Source details are available on the session sensor and in diagnostics. Cloud status can lag local updates;
there is no automatic stale-reading timeout.

## Actual draw and requested limit

The charging gauge shows **Actual current** when an optional measured charger-current sensor in A is selected.
Use measured current, not offered current or a current-limit entity. Without a measured-current sensor, the gauge
shows **Actual charging power** in the power sensor's unit; amps are never estimated from watts.
The requested current limit remains visible below the gauge and as its existing sensor. A 40 A request permits
charging up to that limit; a connected vehicle can still draw 0 A. The observed activity message distinguishes
connected but not drawing power from a disconnected vehicle. Unknown readings remain unknown.

## Charging sources

Switches and an off-peak mode control what Charge Wise does. All start off on a new entry.

- **Charging enabled** is the master switch. While it is off, nothing is charged.
- **Solar charging** calculates available solar headroom as `max(0, measured charger power - net grid power)`. It
  converts that budget to current using the configured single-phase voltage and never requests more than the
  configured limits.
- **Off-peak charging** charges from the grid at the **Off-peak current** while an off-peak window is active. It
  ignores the solar budget and battery protection, but still respects the connection reading, the current maximum
  and the failure stop.
- **Manual override** requests only the **Manual current** and ignores the Solar and off-peak sources.

Solar and off-peak can be on together. Inside a window the higher of the two requested currents wins, and Solar wins a
tie, except during native solar handoff, when the off-peak window takes priority. Outside a window Solar runs as usual.

The switch states and off-peak mode are restored after a Home Assistant restart. A restored Solar source is checked against current
sensor values and held through the restart cooldown before it can start.

Off-peak charging has three modes: **Off**, **On** for recurring scheduled charging, and **On once**.
On once uses the current off-peak period if one is active, otherwise the next period, and returns to Off when that
period ends. Its original end time survives restarts; restarting after that time leaves it Off. On once requires a
configured window. Overlapping or adjacent windows count as one continuous period.

The off-peak mode dropdown replaces the previous off-peak charging switch. Update automations that targeted that switch
to use `select.select_option` with `off`, `on`, or `on_once`.

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
- **Solar production power**: a power sensor with the current solar production.
- **Battery capacity (kWh)**.

Charge Wise works out house consumption as solar production plus grid import plus battery discharge, minus the
charger's power (grid and battery power come from the sensors set on earlier pages). It learns from that: a time-weighted moving average per hour of day,
seeded with the current reading, so the estimate is usable immediately and improves as data arrives. It is saved across
restarts and shown by the diagnostic **Average house consumption** sensor. The **learning window** (default 3 days)
sets how quickly it adapts.

**Battery target by sunset** (default 90 %) sets the battery's energy goal. Select **On** or **On until sunset** under
**EV-first charging**, which also needs **Solar charging**. Forecast surplus means the trusted remaining forecast
minus expected house consumption until sunset.

- **Off** disables EV-first sharing.
- **On** enables recurring EV-first sharing, including on future days.
- **On until sunset** enables sharing for today only and returns to **Off** at sunset. Brief charging pauses do not cancel it.
  The original sunset deadline survives restarts. This choice requires a future sunset for today from the Sun integration;
  after sunset, choose **On** for recurring sharing instead.

The mode survives Home Assistant restarts. When upgrading from the EV-first switch, the new dropdown starts **Off**.
Update automations referencing the removed switch to use the **EV-first charging** select with `select.select_option`
and the option `off`, `on`, or `on_once`.

EV-first sharing stops immediately when forecast surplus is at or below the battery's remaining need. A new sharing
session requires surplus above battery need plus the **EV-first restart surplus margin** (default 25 %).

When sharing is off, **battery-first mode** may still charge the EV from sustained grid export. The battery's charging
power is excluded from this EV budget. An existing sharing session first releases its EV allocation unless genuine
export is already evident, so the EV cannot retain power needed by the battery. Once an export-only session starts,
its measured consumption is included in its budget; export falling toward zero as the EV consumes it does not itself
stop charging. Battery discharge is excluded from that budget.

Export-only starts still follow the configured Solar start threshold, start confirmation, and restart cooldown. A
sustained shortage still follows the ordinary low-solar stop protection. Missing forecast inputs or daylight information
block forecast-managed charging. Manual override and off-peak charging are unaffected.

## Charger-managed solar charging

On the Solar charging page, optionally select a charger solar-mode dropdown and enter its exact full-solar and off
options. This supports dropdown controls, not on/off switches or vendor-specific actions. Charge Wise hands solar
control to the charger when EV-first sharing is inactive, or when the battery reaches 100%. The full-battery handoff
continues until the battery drops below the configured release level (97% by default); battery-first can keep the
handoff active. The full-battery hold survives a restart. Installations without a battery can also use this handoff.

The charger decides its own solar start, stop and current while managing solar. Configure its own safe current limit
and battery priority first: Charge Wise cannot enforce its configured current limits or guarantee battery priority
during handoff. Charge Wise's Solar start threshold, low-solar timing and current smoothing do not control the
charger during handoff. The requested current sensor reads zero because Charge Wise is not requesting a current.

Charging enabled, connection checks, battery-discharge protection and required input checks still apply. Manual
override or an active off-peak window interrupts the handoff. Charge Wise stops the charger while changing ownership,
and disables native solar when the handoff ends. An unavailable native control or a failed mode command stops
charging and reports a control error. The Decision reason sensor can report `native_solar` during handoff; update
automations that assume an exhaustive list of its previous values. Mode confirmation depends on what the charger
integration reports to Home Assistant, which may not immediately reflect the charger's physical state.

Before removing or changing the native solar control, its option values, or the charger switch, turn off **Charging
enabled** and wait for both the charger and native solar mode to report off. Charge Wise checks this before saving.
When unloading the integration, it also waits for both controls to report off; if it cannot confirm that, unloading
fails rather than abandoning the handoff.

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
| Settle time after a change      |     30 s | No further Solar current change while the charger catches up (0 = off)         |
| Solar smoothing window          |     60 s | Averages available solar power so short house loads are ignored (0 = off)      |

The settle time and smoothing window stop the charger hunting up and down when house load changes faster than the
charger's power reading follows. Battery protection reductions ignore the settle time.

For battery protection, Charge Wise reduces the target by the ceiling of the full measured discharge divided by the
configured voltage. If the reduced target would be below the minimum operating current, charging stops. The battery
protection binary sensor is created only when a battery-power entity is configured.

## Safety and unavailable inputs

- For the Solar source, invalid or unavailable grid or charger power stops charging. A configured battery sensor that becomes
  invalid also stops Solar operation.
- If a connection or charger-status sensor is configured, an unknown or disconnected connection holds charging for every source.
- If optional battery or charger status/connection sensors are not configured, the integration cannot provide those protections.
- There is no generic stale-reading timeout or handling of source-specific timestamp attributes. Charge Wise relies
  on each source integration to mark stale readings unavailable.
- Sensor recovery does not change the switches. Solar only resumes after its safety checks and cooldown.
- A failed target or switch command is reported as an error and triggers a best-effort stop command.
- Charge Wise waits for the requested current limit before enabling a normal charger. An OCPP session limit may
  become available only after starting its transaction; that startup is allowed a 30-second confirmation window.
  Missing or unconfirmed current limits fail after 30 seconds. Once the current limit is confirmed, the start
  command gets its own 30-second response window. An unconfirmed
  current change while charging triggers a best-effort stop while Charge Wise waits for acknowledgement.
- Native solar handoff also requires the session current limit to confirm its requested maximum within 30 seconds.
  Identical pending requests are not repeated. A failed confirmation stops the handoff and reports Error.
- If the charger reports enabled but produces no measured charging activity for five minutes, Charge Wise reports Error while
  keeping the charger enabled and its current limit in place. It does not repeat start commands or reboot the charger.
  The error clears automatically when measured charging begins. Explicit paused/finished session statuses and native
  solar mode are exempt from this power check. Normal safety checks and charging windows still apply.
- After a failed or unconfirmed control command, Charge Wise holds charging off. Correct the source problem, then
  turn **Charging enabled** off and on to retry.

## Entities

Each entry creates:

- **Charging enabled**, **Solar charging**, and **Manual override** switches, plus **EV-first charging** and
  **Off-peak charging** dropdowns.
- **Manual current** and **Off-peak current** numbers. On first install both start at the charger maximum; after that
  they keep their last value across restarts.
- **Controller status** sensor with the stable states Off, Waiting, Charging, Paused, and Error.
- **Available solar budget**, **Requested current**, and **Decision reason** sensors.
- **Vehicle connected** and **Vehicle charging** binary sensors, and a **Charger session** sensor. These show observations even when control is off; missing evidence appears as unknown.
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
and any configured battery or charger status/connection sensor is available and valid. The **Decision reason** sensor reports the
specific condition.

### A charger command fails

Confirm that the selected switch and current target are available, that the target accepts amperes, and that the
configured safe maximum is supported by the charger. Review Home Assistant logs and the **Controller status** and
**Decision reason** entities.
