# ChargeWise

## Project Handoff and Development Specification

**Project:** ChargeWise
**Repository:** `ha-charge-wise` (proposed)
**Home Assistant domain:** `charge_wise` (proposed)
**Type:** Custom Home Assistant integration
**Language:** Python
**Distribution goal:** HACS
**Development environment:** VS Code with Codex and/or GitHub Copilot

**Status:** New project. This document describes the intended functionality, lessons from previous Home Assistant automations, and a recommended implementation plan. It is not a claim that these features have already been implemented.

---

## 1. Project Overview

ChargeWise is a hardware-agnostic intelligent EV charging controller for Home Assistant.

Its purpose is to optimize EV charging using:

- Available solar production
- Household electrical consumption
- Home battery state of charge and charging/discharging behavior
- Grid import/export
- Electricity tariffs and time-of-use periods
- EV battery state of charge
- Desired charging completion time
- User-selected charging modes
- Forecasted solar production

ChargeWise should work with existing Home Assistant entities rather than requiring a specific EV charger, solar inverter, battery, or vehicle manufacturer.

A separate project, **MockSolar**, provides a virtual energy system for development and testing.

### Primary design objectives

1. Maximize use of excess solar generation for EV charging.
2. Avoid unnecessary grid imports during solar charging.
3. Prevent the EV charger from unintentionally discharging the home battery.
4. Ensure the EV reaches its desired charge level by a specified deadline when feasible.
5. Support manual charging independently of solar restrictions.
6. Take advantage of inexpensive electricity periods.
7. Minimize unnecessary charger starts, stops, and current adjustments.
8. Remain compatible with multiple chargers and energy systems.
9. Provide transparent charging decisions and useful diagnostics.
10. Never modify or control real hardware without explicit user configuration.
11. Allow flexible configuration of charge priority for EV and home battery.
12. Set target times for charging the EV or home battery.
13. Easily allow manual charging.
14. Support schedulded charging during off peak hours.

---

## 2. Reference Hardware Environment

The first development and testing environment consists of the following equipment.

### Solar and home battery

**Hardware:**

- MockSolar battery, solar, grid, charger and EV.

**Battery sign convention:**

- Positive battery power = discharging
- Negative battery power = charging

**Grid sign convention:**

- Positive grid power = importing
- Negative grid power = exporting

ChargeWise must support configurable sign conventions rather than assuming all hardware uses the same polarity.

#### Existing charger entities

The max and min charger amps should be configuralble.

The initial integration should support chargers exposing switches, number entities, status sensors, and power sensors.

### Electricity tariff

**Utility:** San Diego Gas & Electric
**Plan:** EV-TOU-5 under NEM 3.0

ChargeWise should not hardcode SDG&E rates or schedules. Instead, provide a tariff abstraction supporting:

- User-configured time-of-use periods
- Import price sensors
- Export compensation sensors
- Different weekday/weekend schedules
- Seasonal pricing
- Holidays
- Optional future price forecasts

---

## 3. Charging Modes

The initial implementation should support four modes.

### Mode 1 — Off

Charging is disabled by ChargeWise.

Expected behavior:

- Disable charger output.
- Do not restart charging automatically.
- Continue monitoring sensors.
- Permit mode changes at any time.

### Mode 2 — Solar Surplus

Charge using available solar surplus while respecting home battery protection.

Expected behavior:

- Start charging when sufficient surplus solar is available.
- Adjust charging current as available power changes.
- Reduce charging current when solar production decreases.
- Stop charging when insufficient power remains.
- Avoid sustained home battery discharge.
- Apply hysteresis and cooldown periods to avoid oscillation.
- Allow configuration of priority for either EV or home battery
- Allow setting a time target to hit the desired SOC
- Eventualy add a smart alogirthm based on forcasted solar to prioritze EV earlier in the day if solar production is sufficient.

This is the primary optimization mode.

### Mode 3 — Manual

Charge immediately at a user-selected current.

Expected behavior:

- Ignore solar surplus requirements.
- Ignore battery-discharge restrictions intended specifically for Solar mode.
- Permit grid imports.
- Continue respecting charger hardware limits, EV charging limits, and safety constraints.
- Stop when manually disabled or when an applicable target SOC is reached, according to configured behavior.

Manual mode must be reliable even when solar production is zero.

### Mode 4 — Super Off-Peak

Charge during user-configured low-cost electricity periods.

Expected behavior:

- Determine whether the current time is within an allowed tariff window.
- Start charging during eligible periods.
- Allow charging from the grid.
- Use a configurable charging current.
- Stop or transition to the selected fallback mode when the period ends.
- Eventualy there may be an option to schedule off peak on top of the selected mode.

The implementation should eventually support an optional automatic charging schedule based on tariff prices.

---

## 4. Solar Charging Algorithm

### 4.1 Core power measurements

ChargeWise should accept:

- Solar production
- Total home consumption(With the option to specifiy if this is with our without solar)
- EV charging power
- Grid import/export
- Home battery power
- Home battery SOC

These values may originate from different integrations.

Normalize all power measurements internally to watts.

### 4.2 Avoid double-counting EV consumption

The household load measurement may include the EV charger.

In that case:

**Base home load = Total home load − EV charging power**

This distinction is essential when calculating how much additional power is available for charging.

### 4.3 Solar surplus

A useful starting estimate is:

**Available charging budget = Current EV charging power − Grid import power**

Using signed grid power, a negative grid value represents export.

Example:

- EV charging: 4,000 W
- Grid exporting: 2,000 W
- Grid power: −2,000 W

Available charging budget:

4,000 − (−2,000) = 6,000 W

This represents approximately 6 kW of charging that could be sustained without changing the current grid balance, assuming other loads remain constant.

However, battery behavior must also be considered.

#### Battery-aware charging

When the home battery is charging, ChargeWise may optionally reserve some solar energy for battery charging.

When the home battery is discharging, ChargeWise should avoid interpreting battery-supplied power as available solar surplus.

A configurable battery charging priority should be supported.

Possible policies:

- Prioritize home battery charging.
- Prioritize EV charging.
- Split available surplus.
- Maintain a minimum home battery SOC.
- Charge battery to desired SOC by end of solar production for the day.

The first implementation can use a simpler conservative policy, with advanced allocation added later.

### 4.4 Charging current calculation

For a single-phase charger:

**Current (A) = Available power (W) / Voltage (V)**

At 240 V:

| Available power | Approximate current |
| --------------- | ------------------: |
| 1,440 W         |                 6 A |
| 2,400 W         |                10 A |
| 4,800 W         |                20 A |
| 7,200 W         |                30 A |
| 9,600 W         |                40 A |

Charging current should be clamped to the configured charger minimum and maximum.

When available power is below the minimum sustainable charging power, Solar mode should stop rather than request an invalid current.

The controller should support configurable voltage and phase count. Three-phase chargers require a different power calculation.

### 4.5 Hysteresis and cooldown

Previous Home Assistant automation testing established that immediate reactions to every sensor change cause unnecessary starts and stops.

Initial recommended parameters:

- Control evaluation interval: 5 seconds to 5 minutes, configurable; initial default 30 seconds.
- Minimum solar power to start: approximately 1.8 kW, configurable.
- Low-solar confirmation duration: 90 seconds.
- Restart cooldown: 3 minutes.
- Battery discharge protection threshold: approximately 300 W.
- Minimum current adjustment: 1 A, with optional larger deadband.

These are starting defaults, not universal optimal values.

The implementation should avoid changing charging current unnecessarily.

A restart cooldown should not prevent urgent stops required by safety constraints or user commands.

---

## 5. Important Wallbox / OCPP Behavior

Previous testing revealed an important startup issue.

The Wallbox charger sometimes failed to begin charging when the session-current-limit entity was unavailable or zero.

A reliable startup sequence was:

1. Set maximum charging current to the desired value.
2. Enable charger charge control.
3. Wait approximately 3 seconds.
4. Set the session current limit to a positive value.

The final step may be required even when the session-current-limit entity initially reports `unavailable`.

Previous automations that refused to set the session current limit unless the entity was already numeric could leave the charger enabled but not actually charging.

### Implementation requirement

Create a charger adapter abstraction that supports device-specific startup sequences.

The Wallbox/OCPP adapter should implement the behavior above, with configurable delays and retries.

Do not assume that enabling a charging switch is sufficient to start a charging session.

The adapter should:

- Verify whether charging actually begins.
- Distinguish command success from observed charging power.
- Retry failed startup operations within safe limits.
- Handle temporarily unavailable entities.
- Report actionable errors.
- Avoid uncontrolled retry loops.

Other chargers may require different startup behavior.

---

## 6. Charger Status Model

ChargeWise should normalize charger states internally.

The existing EV Smart Charger integration uses these optional status strings:

| Status             | Meaning                   |
| ------------------ | ------------------------- |
| `charger_free`     | EV disconnected           |
| `charger_wait`     | Connected but idle        |
| `charger_charging` | Actively charging         |
| `charger_end`      | Charging session finished |

ChargeWise should support these values for compatibility, but the internal state model can be more expressive.

Recommended internal states:

- Disconnected
- Connected / idle
- Starting
- Charging
- Pausing
- Paused
- Finished
- Fault
- Unavailable

When a charger power sensor exists, use measured power to confirm actual charging.

When power is unavailable, use the charger status sensor as a fallback.

Do not interpret an enabled charging switch alone as proof that electricity is flowing.

---

## 7. EV Battery SOC and Charging Targets

ChargeWise should optionally accept an EV battery SOC sensor.

This enables more intelligent scheduling and charge completion estimates.

There should be a mechanism for monitoring more than 1 EV in a household.

### Inputs

- Current EV SOC
- Desired target SOC
- EV usable battery capacity in kWh
- Estimated charging efficiency
- Desired completion time
- Maximum charging power

### Required energy calculation

**Energy required (kWh) = Battery capacity × (Target SOC − Current SOC) / 100**

Account for charging losses when estimating energy required from the charger.

Example:

- EV capacity: 80 kWh
- Current SOC: 40%
- Target SOC: 80%
- Required battery energy: 32 kWh
- Charging efficiency: 92%

Estimated AC energy required:

32 / 0.92 ≈ 34.8 kWh

### Departure-aware charging

A future scheduling engine should estimate whether solar-only charging can meet the target by the deadline.

If not, it may use grid electricity according to a user-configurable policy.

Possible behaviors:

- Solar-only regardless of deadline
- Prefer solar, use grid if necessary
- Minimize total charging cost
- Guarantee target SOC when feasible

Do not silently override a user-selected solar-only policy.

SOC sensors may update slowly or be unavailable. ChargeWise must handle stale SOC data without making unsafe assumptions.

---

## 8. Home Battery Protection

Preventing unwanted home battery discharge is a major design requirement.

The system should monitor:

- Battery power
- Battery SOC
- Grid power
- Solar production
- EV charging power

In Solar mode, sustained battery discharge above a configurable threshold should trigger charging-current reduction or suspension.

A previous automation used a threshold of approximately 0.3 kW.

The controller should distinguish between:

- Small transient battery discharge
- Sustained battery discharge
- Intentional battery grid charging
- Battery discharge during utility grid services
- Battery discharge caused by changing household loads

**Important lesson:** A previously used Grid Services Active flag was removed from the automation because it could also become active during intentional Powerwall grid charging.

ChargeWise should not blindly ignore battery protection whenever a Grid Services flag is active.

Use measured power flows and configurable policies instead.

---

## 9. Home Assistant Integration Architecture

Develop ChargeWise as a native custom integration using current Home Assistant development patterns.

Suggested repository structure:

```text
ha-chargewise/
├── custom_components/
│   └── chargewise/
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── config_flow.py
│       ├── coordinator.py
│       ├── controller.py
│       ├── charging_modes.py
│       ├── charger_adapter.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── switch.py
│       ├── number.py
│       ├── select.py
│       ├── time.py
│       ├── strings.json
│       └── translations/
│           └── en.json
├── tests/
├── README.md
├── hacs.json
└── pyproject.toml
```

This is a suggested structure; adapt it to current Home Assistant APIs and conventions.

### Architectural separation

#### Sensor abstraction

Read and normalize external Home Assistant entities.

Responsibilities:

- Convert kW to W when needed.
- Normalize battery/grid sign conventions.
- Validate values.
- Detect stale or unavailable measurements.
- Expose a consistent internal energy snapshot.

#### Charging controller

Calculate desired charging behavior.

Responsibilities:

- Evaluate charging mode.
- Calculate available solar budget.
- Apply battery protection.
- Apply current limits.
- Apply hysteresis and cooldowns.
- Determine whether to start, stop, or adjust charging.

This component should be independent of Home Assistant service calls wherever practical, enabling unit testing.

Some chargers nativley support charging with solar. There should be a handoff mechanism to use the built in solar charging if desired.

#### Charger adapter

Translate charging decisions into actual Home Assistant service calls.

Responsibilities:

- Enable/disable charger.
- Set current limits.
- Implement startup sequences.
- Handle retries and unavailable entities.
- Verify command outcomes.

#### Scheduling engine

Initially optional.

Responsibilities:

- Time-of-use scheduling.
- Charge completion estimates.
- Deadline-based charging.
- Cost optimization.

#### Home Assistant entity platforms

Expose the controller's state and controls to the user.

---

## 10. Proposed ChargeWise Entities

These are suggested entity names, not finalized implementation requirements.

### User controls

| Entity                                   | Purpose                               |
| ---------------------------------------- | ------------------------------------- |
| `select.chargewise_mode`                 | Off / Solar / Manual / Super Off-Peak |
| `number.chargewise_manual_current`       | Manual charging amps                  |
| `number.chargewise_target_soc`           | Desired EV SOC                        |
| `number.chargewise_min_home_battery_soc` | Battery protection threshold          |
| `number.chargewise_solar_reserve`        | Power reserve / buffer                |
| `time.chargewise_completion_time`        | Desired charging deadline             |
| `switch.chargewise_deadline_assist`      | Permit grid charging to meet deadline |

### Diagnostic sensors

| Entity                                    | Purpose                        |
| ----------------------------------------- | ------------------------------ |
| `sensor.chargewise_status`                | Controller state               |
| `sensor.chargewise_available_solar`       | Available charging budget      |
| `sensor.chargewise_target_current`        | Requested charger current      |
| `sensor.chargewise_actual_charging_power` | Observed charging power        |
| `sensor.chargewise_charging_reason`       | Explanation for current action |
| `sensor.chargewise_estimated_completion`  | Estimated charge completion    |
| `sensor.chargewise_next_cheap_period`     | Next eligible tariff window    |

### Diagnostic binary sensors

- Solar surplus available
- Home battery protection active
- Charger cooldown active
- EV connected
- EV actively charging
- Charging target reached

Support multiple ChargeWise configuration entries where practical, with entity IDs uniquely assigned by Home Assistant.

---

## 11. User Interface and Configuration

The integration should use a Home Assistant config flow rather than requiring users to edit YAML.

### Initial configuration

Allow users to select:

**Energy inputs**

- Solar power sensor
- Grid power sensor
- Home load sensor
- Battery power sensor
- Battery SOC sensor

**Charger inputs and controls**

- Charging control switch
- Maximum current number entity
- Session current limit entity, optional
- Charging power sensor
- Charger status sensor
- Charger minimum and maximum amps
- Charger voltage and phase count

**EV inputs**

- EV SOC sensor, optional
- Battery capacity
- Target SOC

**Charging preferences**

- Default charging mode
- Solar reserve
- Home battery protection threshold
- Current adjustment deadband
- Start/stop hysteresis
- Restart cooldown

Not all optional sensors should be mandatory. The integration should degrade gracefully when capabilities are missing.

### Dashboard

ChareWise should include a mondern elgenant and clean dashboard.

A suggested dashboard should show:

- Current mode
- Solar generation
- Home load
- Grid import/export
- Battery SOC and power
- EV charging power
- Available charging budget
- Target and actual charging current
- EV SOC and target
- Next scheduled charging period
- Current charging decision and reason

A useful feature would be a detailed explanation of why ChargeWise is charging, waiting, or stopped.

For example:

"Solar charging paused: home battery discharging at 520 W for 90 seconds."

---

## 12. Reliability and Safety

ChargeWise will control a real electrical load. The implementation must be conservative and predictable.

Required behaviors:

1. Respect configured charger minimum and maximum currents.
2. Never request an invalid charging current.
3. Handle unavailable sensors safely.
4. Do not assume stale measurements are current.
5. Prevent repeated uncontrolled service calls.
6. Handle Home Assistant restarts.
7. Avoid automatically resuming charging in Off mode.
8. Log significant charging decisions and errors.
9. Provide a clear controller fault state.
10. Allow users to disable ChargeWise control immediately.

A charger fault or unavailable state should not trigger repeated start commands.

The integration should define an explicit fail-safe policy for missing solar, grid, battery, or charger data.

For Solar mode, the conservative default should be to suspend automated charging if the required measurements are unavailable beyond a configurable grace period.

Do not assume that stopping ChargeWise can override all hardware-level charging behaviors; charger hardware and manufacturer safety controls remain authoritative.

---

## 13. MockSolar Integration Testing

MockSolar is a separate Home Assistant simulation project designed specifically for testing energy integrations.

It provides simulated:

- Solar production
- Home consumption
- Home battery SOC
- Battery charging/discharging power
- Grid import/export
- EV charging power
- Charger enable/disable
- Charger current limits
- Charger status
- EV battery SOC

ChargeWise should be tested against MockSolar before connecting it to real devices.

### Essential test scenarios

| Scenario                               | Expected ChargeWise behavior                      |
| -------------------------------------- | ------------------------------------------------- |
| Large solar surplus                    | Start charging and increase current               |
| Solar surplus decreases                | Reduce charging current                           |
| Solar below minimum                    | Stop after hysteresis delay                       |
| Solar returns                          | Restart after cooldown                            |
| Home battery begins discharging        | Reduce or stop charging                           |
| Home battery SOC falls below threshold | Apply configured protection                       |
| Grid begins importing                  | Reduce charging when Solar mode requires it       |
| User selects Manual                    | Charge at manual current                          |
| User selects Off                       | Stop charging                                     |
| Charger becomes unavailable            | Enter safe fault/wait state                       |
| EV unplugged                           | Do not attempt charging                           |
| EV reaches target SOC                  | Stop according to configured target policy        |
| Super Off-Peak begins                  | Start scheduled charging                          |
| Super Off-Peak ends                    | Stop or transition according to configured policy |
| Home Assistant restarts                | Restore state safely                              |

Include automated unit tests for the charging decision engine, with mocked Home Assistant service calls.

Also test inconsistent sensor values, delayed charger responses, stale SOC, transient battery discharge, and charging-power feedback that disagrees with commanded state.

---

## 14. Implementation Phases

### Phase 1 — Minimum Viable Integration

Focus on reliable basic charging.

Implement:

- Home Assistant configuration flow
- Energy sensor selection
- Charger entity selection
- Off mode
- Manual mode
- Solar mode
- Charging current calculation
- Battery discharge protection
- Hysteresis and cooldowns
- Basic diagnostic sensors
- MockSolar testing

The goal is to replace the existing YAML charging automation with a maintainable native integration.

### Phase 2 — Reliability and Compatibility

Add:

- Charger adapter architecture
- Wallbox/OCPP-specific startup handling
- Charger status normalization
- Better error handling
- Retry limits
- Sensor availability monitoring
- More comprehensive tests
- Diagnostics and logging

### Phase 3 — Tariff-Aware Charging

Add:

- Super Off-Peak mode
- Configurable tariff schedules
- Electricity price sensors
- Time-of-use optimization
- Import/export cost awareness

### Phase 4 — EV SOC and Departure Planning

Add:

- EV battery SOC monitoring
- Target SOC
- Battery capacity
- Estimated charging duration
- Completion deadlines
- Solar-first charging with optional grid assistance

### Phase 5 — Advanced Optimization

Potential future features:

- Solar generation forecasts
- Household consumption forecasts
- Battery charge/discharge forecasting
- Multi-EV support
- Multi-charger coordination
- Dynamic electricity prices
- NEM 3.0 export compensation optimization
- Energy cost and savings reporting
- Automated charging plans

These features should not complicate the initial minimum viable implementation.

---

## 15. Development Instructions for Codex / Copilot

You are developing **ChargeWise**, a Home Assistant custom integration for intelligent EV charging.

The project is intended to replace an existing set of Home Assistant YAML automations that manage a Wallbox Pulsar Plus charger using Tesla Powerwall solar, battery, grid, and household power sensors.

The new implementation must be hardware-agnostic, testable, reliable, and compatible with current Home Assistant development practices.

### Initial tasks

1. Inspect the existing repository and identify any code already present. The starting point is a blueprint integration template so we will need to remove that code.
2. Review the latest Home Assistant integration development conventions.
3. Review the relevant behavior of `antbald/ha-ev-smart-charger` as a reference, without assuming its implementation or licensing permits copying.
4. Propose the initial architecture and entity model.
5. Implement the minimum viable configuration flow.
6. Implement a pure-Python charging decision engine.
7. Implement the charger control adapter.
8. Add Off, Manual, and Solar charging modes.
9. Add unit tests using simulated energy snapshots.
10. Test against MockSolar before connecting real hardware.

### Engineering requirements

- Prefer asynchronous Home Assistant APIs.
- Avoid blocking the event loop.
- Use standard entity platforms and unique IDs.
- Use Home Assistant config entries and options flows.
- Separate device commands from charging decisions.
- Keep the charging algorithm independently unit-testable.
- Provide meaningful diagnostics and logging.
- Follow current Home Assistant quality and HACS requirements.
- Avoid unnecessary third-party dependencies.
- Do not assume every charger has a session-current-limit entity.
- Do not assume every vehicle exposes SOC.
- Do not assume battery or grid power signs are consistent between vendors.
- Preserve a clear distinction between desired charging state and observed charging state.

### Important development constraint

**Do not implement all planned features at once.**

Start with a stable, well-tested Solar/Manual/Off controller. Build the architecture so scheduling, forecasting, and cost optimization can be added later without rewriting the core.

### First requested deliverable

Before writing the full integration, produce:

1. A proposed repository structure.
2. A component architecture.
3. A Home Assistant entity and configuration model.
4. A charging state machine design.
5. A detailed Phase 1 implementation plan.
6. A list of unresolved design decisions requiring user input.

Then begin implementation incrementally, keeping the integration functional and testable at each stage.

---

## 16. Key Design Philosophy

ChargeWise should behave like an intelligent energy manager, not simply an automation that turns a charger on and off.

It should continuously answer four questions:

**Can I charge?**
Based on vehicle connection, charger availability, mode, and safety constraints.

**Should I charge?**
Based on solar availability, battery priorities, electricity prices, and charging deadlines.

**How fast should I charge?**
Based on available power, charger limits, battery behavior, and user preferences.

**Why am I making this decision?**
Every charging action should be explainable through diagnostic entities and logs.

The result should be an intuitive, reliable, and extensible Home Assistant integration that makes efficient EV charging accessible without requiring users to write complex YAML automations.
