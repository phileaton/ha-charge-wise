"""Grid-search controller and EV-first settings over the stored scenarios.

Usage: python -m tests.scenarios.sweep [--max-starts 3] [--top 15]
"""

import argparse
from dataclasses import dataclass, replace
import itertools

from .replay import INSTALL_CONTROLLER, INSTALL_EV_FIRST, DayResult, available_days, replay  # noqa: TID251

GRID = {
    "low_solar_confirmation_s": [90, 300, 600, 900],
    "cooldown_s": [90, 300, 900],
    "solar_start_w": [1600, 2200, 3000],
    "smoothing_window_s": [60, 300],
    "margin": [10, 25, 40],
}


@dataclass(frozen=True)
class Outcome:
    """Aggregate result of one settings combination across all days."""

    settings: dict[str, float]
    worst_starts: int
    mean_starts: float
    mean_ev_kwh: float
    mean_grid_kwh: float


def evaluate(settings: dict[str, float], days: list[str]) -> Outcome:
    """Replay every day with the settings and aggregate the results."""
    margin = settings["margin"]
    controller = replace(INSTALL_CONTROLLER, **{key: int(value) for key, value in settings.items() if key != "margin"})
    results: list[DayResult] = replay(
        days,
        controller_config=controller,
        ev_first_config=replace(INSTALL_EV_FIRST, release_margin_percent=margin),
    )
    count = len(results)
    return Outcome(
        settings,
        max(item.starts for item in results),
        sum(item.starts for item in results) / count,
        sum(item.ev_kwh for item in results) / count,
        sum(item.ev_grid_kwh for item in results) / count,
    )


def main() -> None:
    """Run the sweep and print the best combinations that respect the start limit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-starts", type=int, default=3)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    days = available_days()
    keys = list(GRID)
    outcomes = [evaluate(dict(zip(keys, values, strict=True)), days) for values in itertools.product(*GRID.values())]
    allowed = [item for item in outcomes if item.worst_starts <= args.max_starts]
    print(f"{len(outcomes)} combinations, {len(allowed)} with at most {args.max_starts} starts on every day")  # noqa: T201
    ranked = sorted(allowed or outcomes, key=lambda item: (item.mean_grid_kwh, -item.mean_ev_kwh))
    for item in ranked[: args.top]:
        print(  # noqa: T201
            f"starts max {item.worst_starts:2d} avg {item.mean_starts:4.1f} | ev {item.mean_ev_kwh:5.1f} kWh "
            f"| grid {item.mean_grid_kwh:5.2f} kWh | {item.settings}"
        )


if __name__ == "__main__":
    main()
