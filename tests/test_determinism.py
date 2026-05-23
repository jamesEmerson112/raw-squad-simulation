"""Determinism: same seed must produce identical battles."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pygame

pygame.init()

from encapsulated_spark.scenarios import capture_the_hill, woods_and_wall  # noqa: E402
from encapsulated_spark.sim import FIXED_DT  # noqa: E402


def _fingerprint(sim) -> tuple:
    cp = sim.world.capture_point
    cp_state = (
        round(cp.meters["red"], 6) if cp else 0.0,
        round(cp.meters["blue"], 6) if cp else 0.0,
        cp.winner if cp else None,
    )
    units = tuple(
        (
            u.id,
            u.alive,
            u.broken,
            round(u.pos.x, 6),
            round(u.pos.y, 6),
            round(u.hp, 6),
        )
        for u in sim.units
    )
    return (round(sim.t, 6), cp_state, units)


def _run(factory, **kwargs):
    sim = factory(**kwargs)
    for _ in range(800):
        sim.step(FIXED_DT)
        if sim.winner() is not None:
            break
    return _fingerprint(sim)


def test_woods_and_wall_seed_repeats():
    fp1 = _run(woods_and_wall, red_count=24, blue_count=24, seed=42)
    fp2 = _run(woods_and_wall, red_count=24, blue_count=24, seed=42)
    assert fp1 == fp2, "same seed must yield identical battle state"


def test_capture_the_hill_seed_repeats():
    fp1 = _run(capture_the_hill, red_count=24, blue_count=24, seed=7)
    fp2 = _run(capture_the_hill, red_count=24, blue_count=24, seed=7)
    assert fp1 == fp2


def test_different_seeds_diverge():
    fp1 = _run(woods_and_wall, red_count=24, blue_count=24, seed=1)
    fp2 = _run(woods_and_wall, red_count=24, blue_count=24, seed=2)
    assert fp1 != fp2, "different seeds should diverge"


if __name__ == "__main__":
    test_woods_and_wall_seed_repeats(); print("woods_and_wall: OK")
    test_capture_the_hill_seed_repeats(); print("capture_the_hill: OK")
    test_different_seeds_diverge(); print("different_seeds: OK")
