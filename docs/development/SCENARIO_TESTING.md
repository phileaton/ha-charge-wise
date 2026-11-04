# Scenario Replay Testing

Recorded days of real solar, grid, battery and forecast readings, replayed through ChargeWise's actual decision logic.
Use it to check that the controller behaves sensibly on real weather, and to compare settings (for example the EV-first
release margin) on identical days before changing them on the live install.

## What it is, and is not

- ✅ Runs the real `ChargeWiseController`, `evaluate_ev_first`, `ForecastAccuracy` and `HouseLoadProfile` with a
  simulated clock, stepping every 30 seconds.
- ✅ Good for decision logic: starts and stops, flapping, pauses while a budget exists, EV-first timing, comparing two
  settings on the same days.
- ❌ Not a full simulation. The charger is modelled as drawing the requested current instantly. Its recorded draw is
  removed from the recorded grid power and the simulated draw is added back, but solar and battery stay exactly as
  recorded because the real battery would have reacted differently. Treat absolute kWh figures as indicative only.
- ❌ It does not run Home Assistant, the OCPP integration or the coordinator, so command timing (such as the 30 s
  pending-switch grace window) is covered by the integration tests instead.

## Layout

| Path                                | Purpose                                                      |
| ----------------------------------- | ------------------------------------------------------------ |
| `script/export-scenario`            | Wrapper that runs the exporter inside the project virtualenv |
| `tests/scenarios/export.py`         | Reads the recorder database and writes one fixture per day   |
| `tests/scenarios/data/<date>.json`  | Committed fixtures, about 100 KB each                        |
| `tests/scenarios/replay.py`         | The replay harness and the per-day result summary            |
| `tests/scenarios/test_scenarios.py` | Assertions run by `script/test` over every stored fixture    |

## Recording new days

The recorder purges old history (`purge_keep_days` in `config/configuration.yaml`, currently 14), so export a day
before it is purged. A day is only complete after local midnight.

```bash
./script/export-scenario 2026-11-04
./script/export-scenario 2026-11-05 2026-11-06 --timezone America/Los_Angeles
```

Options:

- `--database PATH` — recorder database, default `config/home-assistant_v2.db`.
- `--timezone ZONE` — the Home Assistant time zone; it defines where a day starts and ends.
- `--battery-sign positive|negative` — which sign means discharging in your battery sensor. The fixture stores
  discharge as positive.
- `--entity KEY=ENTITY_ID` — override a source sensor. Keys: `solar_w`, `grid_w`, `battery_w`, `battery_level`,
  `charger_w`, `forecast_remaining_kwh`, `forecast_today_kwh`. The defaults are this install's entity ids.

Values are converted from the sensor's unit to W, kWh and percent. The exporter fails when a required series has no
data for the day, or the panels never produced power. The charger series is optional and only exists for days when the
charger sensor was recorded.

Each fixture holds step-held `[seconds since local midnight, value]` points per series, plus the date, time zone,
derived sunrise and sunset (first and last time solar exceeded 50 W) and the source entity ids. `sun.sun` is not
recorded on this install, so sunrise and sunset are derived rather than read.

Fixtures contain readings only, with no credentials or location.

## Running a replay

```bash
source script/.lib/output.sh && activate_venv
python -m tests.scenarios.replay
```

```text
date        starts stops ev_kWh  charging_min  ev_first_min  solar_kWh  max_pause_with_budget_min
2026-11-02     13    13    18.4          302           646       71.5            0
```

| Column                      | Meaning                                                                        |
| --------------------------- | ------------------------------------------------------------------------------ |
| `starts`, `stops`           | Charger enable and disable transitions; high numbers indicate flapping         |
| `ev_kWh`                    | Simulated energy delivered to the EV                                           |
| `charging_min`              | Minutes the charger was on                                                     |
| `ev_first_min`              | Minutes EV-first was active                                                    |
| `solar_kWh`                 | Recorded solar production for the day                                          |
| `max_pause_with_budget_min` | Longest stretch paused while the available budget was at least `solar_start_w` |

Each `DayResult` also has a `timeline` of `(time, status, reason, charger_enabled, amps)` entries, one per change.
Print it to see exactly when and why the controller acted.

Days are replayed in date order and the house load profile carries over, as it does on the live install. The first
stored day therefore starts with an empty profile.

## Comparing settings

`replay()` accepts a `ControllerConfig`, an `EvFirstConfig` (or `None` to disable EV-first) and the house-load window.
The defaults, `INSTALL_CONTROLLER` and `INSTALL_EV_FIRST`, mirror the live options; keep them in step when options
change on the install.

```python
from tests.scenarios.replay import INSTALL_EV_FIRST, available_days, replay, summary, with_margin

days = available_days()
print(summary(replay(days, ev_first_config=with_margin(INSTALL_EV_FIRST, 10))))
print(summary(replay(days, ev_first_config=with_margin(INSTALL_EV_FIRST, 25))))
```

For controller thresholds use `dataclasses.replace(INSTALL_CONTROLLER, cooldown_s=180)`.

## The tests

`script/test` runs `tests/scenarios/test_scenarios.py` over every fixture in `data/`, and skips when there are none.

- Fixtures are well-formed and in time order.
- Replays are deterministic.
- No pause longer than 10 minutes while a start-sized budget is available.
- At most 20 starts per day, and starts and stops differ by at most one.
- EV energy never exceeds the day's solar.
- A larger release margin never holds EV-first for less time.

These are guard rails, not tuning targets. Tighten them as the controller is tuned, and add an assertion for any
regression a replay uncovers.

## Adding a regression scenario

1. Export the day that showed the problem.
2. Replay it and read the `timeline` around the problem time.
3. Add a test in `test_scenarios.py` that asserts the corrected behaviour for that date.
4. Keep the fixture. Recorder history is purged, so the fixture is the only permanent copy.
