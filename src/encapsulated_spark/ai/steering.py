"""Steering helpers: pick cover waypoint, rout vector."""

from __future__ import annotations

import math
import random

import pygame

from ..terrain import CoverPatch
from ..units import Unit

Vec = pygame.math.Vector2


def assign_cover_waypoint(
    unit: Unit, cover_patches: list[CoverPatch], rng: random.Random
) -> None:
    """High-discipline units route through their nearest forward cover patch.

    Called once per unit at scenario start.
    """
    if unit.target_pos is None or not cover_patches:
        return
    if rng.random() > unit.discipline:
        return  # this unit doesn't prioritize cover
    # Pick the cover patch nearest to the path between current pos and target.
    best: CoverPatch | None = None
    best_score = float("inf")
    direction = (unit.target_pos - unit.pos)
    travel_dist = direction.length()
    if travel_dist < 1.0:
        return
    direction = direction / travel_dist
    for c in cover_patches:
        center = Vec(c.x + c.w / 2, c.y + c.h / 2)
        offset = center - unit.pos
        # Project onto direction; reject patches behind or past the target.
        along = offset.dot(direction)
        if along < 10.0 or along > travel_dist - 10.0:
            continue
        perp = (offset - direction * along).length()
        score = perp + along * 0.05  # prefer near-path, mildly prefer closer
        if score < best_score:
            best_score = score
            best = c
    if best is not None:
        unit.cover_waypoint = Vec(best.x + best.w / 2, best.y + best.h / 2)


def current_steering_target(unit: Unit) -> Vec | None:
    """Steer toward cover waypoint first, then the real target."""
    if unit.broken:
        return None  # rout handled separately
    if unit.cover_waypoint is not None:
        if (unit.cover_waypoint - unit.pos).length() > 12.0:
            return unit.cover_waypoint
        # arrived at cover — drop waypoint, head for real target
        unit.cover_waypoint = None
    return unit.target_pos


def rout_target(unit: Unit, enemy_centroid: Vec, world_size: tuple[float, float]) -> Vec:
    """Broken units run away from the enemy centroid toward the nearest edge."""
    away = unit.pos - enemy_centroid
    if away.length_squared() < 1.0:
        away = Vec(1, 0)
    away = away.normalize()
    return unit.pos + away * 500.0
