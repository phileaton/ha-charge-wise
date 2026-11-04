"""Export one local day of readings from the Home Assistant recorder into a replayable scenario fixture.

Usage (through the wrapper): script/export-scenario 2026-11-03 [2026-11-02 ...]

Values are normalised to W, kWh and percent, and the battery is stored with discharge positive.
Only readings are written; no coordinates or identifiers beyond the entity ids are stored.
"""

import argparse
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_DATABASE = Path(__file__).parents[2] / "config" / "home-assistant_v2.db"
DEFAULT_TIMEZONE = "America/Los_Angeles"

DEFAULT_ENTITIES = {
    "solar_w": "sensor.powerwall_10_0_3_127_solar_power",
    "grid_w": "sensor.powerwall_10_0_3_127_site_power",
    "battery_w": "sensor.powerwall_10_0_3_127_battery_power",
    "battery_level": "sensor.powerwall_10_0_3_127_charge",
    "charger_w": "sensor.charger_power_active_import",
    "forecast_remaining_kwh": "sensor.solcast_pv_forecast_forecast_remaining_today",
    "forecast_today_kwh": "sensor.solcast_pv_forecast_forecast_today",
}

_POWER = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0}
_ENERGY = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}
_KIND = {
    "solar_w": _POWER,
    "grid_w": _POWER,
    "battery_w": _POWER,
    "charger_w": _POWER,
    "forecast_remaining_kwh": _ENERGY,
    "forecast_today_kwh": _ENERGY,
    "battery_level": {"%": 1.0},
}
_REQUIRED = ("solar_w", "grid_w", "battery_w", "battery_level", "forecast_remaining_kwh", "forecast_today_kwh")
_ACTIVE_SOLAR_W = 50.0


def _unit_factor(connection: sqlite3.Connection, entity_id: str, factors: dict[str, float]) -> float:
    """Return the factor for the entity's most recent unit, so every row is converted the same way."""
    row = connection.execute(
        """
        SELECT a.shared_attrs FROM states s
        JOIN states_meta m ON m.metadata_id = s.metadata_id
        JOIN state_attributes a ON a.attributes_id = s.attributes_id
        WHERE m.entity_id = ? ORDER BY s.last_updated_ts DESC LIMIT 1
        """,
        (entity_id,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"{entity_id}: no history in the recorder")
    unit = json.loads(row[0]).get("unit_of_measurement")
    if unit not in factors:
        raise SystemExit(f"{entity_id}: unsupported unit {unit!r}")
    return factors[unit]


def _read_series(
    connection: sqlite3.Connection,
    entity_id: str,
    factor: float,
    start_ts: float,
    end_ts: float,
) -> list[list[float]]:
    """Return [seconds since start, value] rows, seeded with the value held at the start of the day."""
    rows = connection.execute(
        """
        SELECT s.last_updated_ts, s.state FROM states s
        JOIN states_meta m ON m.metadata_id = s.metadata_id
        WHERE m.entity_id = ? AND s.last_updated_ts < ? ORDER BY s.last_updated_ts
        """,
        (entity_id, end_ts),
    ).fetchall()
    series: list[list[float]] = []
    seed: float | None = None
    for timestamp, state in rows:
        try:
            value = float(state) * factor
        except TypeError, ValueError:
            continue
        if timestamp < start_ts:
            seed = value
            continue
        if series and series[-1][1] == value:
            continue
        series.append([round(timestamp - start_ts, 1), round(value, 3)])
    if seed is not None and (not series or series[0][0] > 0):
        series.insert(0, [0.0, round(seed, 3)])
    return series


def export_day(
    connection: sqlite3.Connection,
    day: date,
    *,
    entities: dict[str, str],
    timezone: str,
    battery_sign: str,
) -> dict[str, Any]:
    """Build the scenario document for one local calendar day."""
    zone = ZoneInfo(timezone)
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    series: dict[str, list[list[float]]] = {}
    for key, entity_id in entities.items():
        factor = _unit_factor(connection, entity_id, _KIND[key])
        if key == "battery_w" and battery_sign == "negative":
            factor = -factor
        series[key] = _read_series(connection, entity_id, factor, start.timestamp(), end.timestamp())
    missing = [key for key in _REQUIRED if not series.get(key)]
    if missing:
        raise SystemExit(f"{day}: no data for {', '.join(missing)}")

    producing = [point[0] for point in series["solar_w"] if point[1] > _ACTIVE_SOLAR_W]
    if not producing:
        raise SystemExit(f"{day}: the panels never produced power, nothing to replay")
    return {
        "date": day.isoformat(),
        "timezone": timezone,
        "start_utc": start.astimezone(UTC).isoformat(),
        "seconds": int((end - start).total_seconds()),
        "sunrise_s": producing[0],
        "sunset_s": producing[-1],
        "entities": entities,
        "series": series,
    }


def main(argv: list[str] | None = None) -> None:
    """Export each requested day to tests/scenarios/data/<date>.json."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("days", nargs="+", type=date.fromisoformat, help="Local dates (YYYY-MM-DD)")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="The Home Assistant time zone")
    parser.add_argument("--battery-sign", choices=("positive", "negative"), default="positive")
    parser.add_argument(
        "--entity",
        action="append",
        default=[],
        metavar="KEY=ENTITY_ID",
        help=f"Override a source entity; keys: {', '.join(DEFAULT_ENTITIES)}",
    )
    args = parser.parse_args(argv)

    entities = dict(DEFAULT_ENTITIES)
    for item in args.entity:
        key, _, entity_id = item.partition("=")
        if key not in entities or not entity_id:
            parser.error(f"unknown or empty --entity {item!r}")
        entities[key] = entity_id

    connection = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for day in args.days:
            document = export_day(
                connection,
                day,
                entities=entities,
                timezone=args.timezone,
                battery_sign=args.battery_sign,
            )
            path = DATA_DIR / f"{day.isoformat()}.json"
            path.write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8")
            points = sum(len(rows) for rows in document["series"].values())
            print(f"{path.name}: {points} points")  # noqa: T201
    finally:
        connection.close()


if __name__ == "__main__":
    main()
