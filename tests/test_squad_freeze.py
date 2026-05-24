"""TDD probe for the 'frozen middle' bug.

Runs `capture_the_hill` headless and samples every squad's centroid every
half second. Writes the timeline to a JSONL file, then asserts that no
squad's centroid stays still for 5+ seconds while enemies remain alive.

This is a regression test for the frozen-middle bug. The JSONL log remains
useful when tuning contact behavior because it shows squad centroid motion
through the opening fight.

Run:
    .venv/bin/python tests/test_squad_freeze.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

import pygame  # noqa: E402

pygame.init()

from encapsulated_spark.hierarchy import squad_centroid  # noqa: E402
from encapsulated_spark.scenarios import capture_the_hill  # noqa: E402
from encapsulated_spark.sim import FIXED_DT  # noqa: E402

# --- knobs the user can retune without re-reading the test --------------
SCENARIO_NAME = "capture_the_hill"
SEED = 1
RED_COUNT = 40
BLUE_COUNT = 40
MAX_SIM_SECONDS = 60.0
SAMPLE_EVERY_TICKS = 30                  # = 0.5 sim-seconds
WARMUP_SECONDS = 4.0                     # ignore the initial march phase
FREEZE_WINDOW_SECONDS = 5.0              # how long "frozen" must persist
FREEZE_RADIUS_PX = 8.0                   # max centroid drift inside window
MIN_ALIVE_MEMBERS = 3                    # ignore wiped-out squads
OUTPUT_PATH = _REPO / "runs" / f"freeze_probe-{SCENARIO_NAME}-seed{SEED}.jsonl"


def _sample_centroids(sim) -> list[dict]:
    """One snapshot row per alive-or-just-died squad at the current sim time."""
    rows: list[dict] = []
    for sq in sim.squads.values():
        c = squad_centroid(sq, sim.units_by_id)
        alive_members = sum(
            1 for mid in sq.member_ids if sim.units_by_id[mid].alive
        )
        rows.append({
            "t": round(sim.t, 3),
            "squad_id": sq.id,
            "team": sq.team,
            "cx": round(c.x, 2) if c is not None else None,
            "cy": round(c.y, 2) if c is not None else None,
            "alive_members": alive_members,
        })
    return rows


def _enemies_alive_at(samples: list[dict]) -> dict[str, int]:
    """Per-team alive-member totals from one t-slice of samples."""
    totals = {"red": 0, "blue": 0}
    for row in samples:
        totals[row["team"]] += row["alive_members"]
    return totals


def _find_frozen_windows(timeline: list[list[dict]]) -> list[dict]:
    """Slide a FREEZE_WINDOW_SECONDS window across each squad's track.

    A squad-window is frozen iff:
      - all samples have alive_members >= MIN_ALIVE_MEMBERS
      - max centroid displacement from the window mean < FREEZE_RADIUS_PX
      - the opposite team still has alive units across the whole window
      - the window's start time >= WARMUP_SECONDS
    """
    if not timeline:
        return []
    # Index by squad_id → list of (t, cx, cy, alive_members)
    per_squad: dict[int, list[dict]] = {}
    times = []
    enemy_alive_at_t: list[dict[str, int]] = []
    for slice_ in timeline:
        if not slice_:
            continue
        t = slice_[0]["t"]
        times.append(t)
        enemy_alive_at_t.append(_enemies_alive_at(slice_))
        for row in slice_:
            per_squad.setdefault(row["squad_id"], []).append(row)
    if len(times) < 2:
        return []
    dt = times[1] - times[0]
    window_len = max(1, int(round(FREEZE_WINDOW_SECONDS / dt)))
    frozen: list[dict] = []
    for sid, track in per_squad.items():
        if len(track) < window_len:
            continue
        team = track[0]["team"]
        enemy_team = "blue" if team == "red" else "red"
        for i in range(0, len(track) - window_len + 1):
            window = track[i:i + window_len]
            if window[0]["t"] < WARMUP_SECONDS:
                continue
            if any(r["alive_members"] < MIN_ALIVE_MEMBERS for r in window):
                continue
            if any(
                enemy_alive_at_t[i + k][enemy_team] == 0
                for k in range(window_len)
            ):
                continue
            xs = [r["cx"] for r in window if r["cx"] is not None]
            ys = [r["cy"] for r in window if r["cy"] is not None]
            if len(xs) < window_len:
                continue
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            max_disp = max(math.hypot(x - mx, y - my) for x, y in zip(xs, ys))
            if max_disp < FREEZE_RADIUS_PX:
                frozen.append({
                    "squad_id": sid,
                    "team": team,
                    "t_start": window[0]["t"],
                    "t_end": window[-1]["t"],
                    "max_disp": round(max_disp, 2),
                    "mean_cx": round(mx, 1),
                    "mean_cy": round(my, 1),
                    "alive_members_at_start": window[0]["alive_members"],
                })
                break  # one frozen window per squad is enough to flag it
    return frozen


def test_no_squad_freezes_in_the_middle() -> None:
    sim = capture_the_hill(
        red_count=RED_COUNT, blue_count=BLUE_COUNT, seed=SEED,
    )
    max_ticks = int(MAX_SIM_SECONDS / FIXED_DT)

    timeline: list[list[dict]] = []
    for tick in range(max_ticks):
        if tick % SAMPLE_EVERY_TICKS == 0:
            timeline.append(_sample_centroids(sim))
        sim.step(FIXED_DT)
        if sim.winner() is not None:
            timeline.append(_sample_centroids(sim))
            break

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        for slice_ in timeline:
            for row in slice_:
                f.write(json.dumps(row) + "\n")

    frozen = _find_frozen_windows(timeline)
    print(f"sim ended at t={sim.t:.1f}s, winner={sim.winner()}")
    print(f"timeline samples: {len(timeline)} slices × {len(timeline[0]) if timeline else 0} squads")
    print(f"jsonl: {OUTPUT_PATH}")
    if frozen:
        print(f"\nFROZEN WINDOWS ({len(frozen)}):")
        print(
            f"  {'sid':>3}  {'team':<4}  {'t_start':>7}  {'t_end':>6}  "
            f"{'max_disp':>8}  {'mean_xy':>14}  {'alive':>5}"
        )
        for w in frozen:
            print(
                f"  {w['squad_id']:>3}  {w['team']:<4}  "
                f"{w['t_start']:>7.1f}  {w['t_end']:>6.1f}  "
                f"{w['max_disp']:>8.2f}  "
                f"({w['mean_cx']:>5.0f}, {w['mean_cy']:>5.0f})  "
                f"{w['alive_members_at_start']:>5}"
            )
    assert not frozen, (
        f"{len(frozen)} squad-windows look frozen for >= "
        f"{FREEZE_WINDOW_SECONDS:.0f}s with enemies still alive — "
        f"see {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    try:
        test_no_squad_freezes_in_the_middle()
        print("\nno-freeze: OK")
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)
