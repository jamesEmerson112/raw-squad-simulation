"""Terrain: walls, cover, trees, elevation. Plus the LOS / collision helpers."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

Vec = pygame.math.Vector2


@dataclass(frozen=True)
class Wall:
    """Solid line segment. Blocks LOS and movement."""
    a: tuple[float, float]
    b: tuple[float, float]


@dataclass(frozen=True)
class CoverPatch:
    """Rectangle of cover (low wall / sandbag line). Units inside take less damage."""
    x: float
    y: float
    w: float
    h: float
    damage_factor: float = 0.5  # incoming damage multiplier

    def contains(self, p: Vec) -> bool:
        return self.x <= p.x <= self.x + self.w and self.y <= p.y <= self.y + self.h


@dataclass(frozen=True)
class Tree:
    """Circular tree. Partially blocks LOS; pushes units out."""
    cx: float
    cy: float
    r: float = 10.0
    occlude_chance: float = 0.4  # per shot crossing the disk


@dataclass
class ElevationMap:
    """Coarse heightmap covering [0, world.width] x [0, world.height]."""
    cells_x: int
    cells_y: int
    world_w: float
    world_h: float
    heights: list[list[float]] = field(default_factory=list)  # heights[y][x]

    @classmethod
    def flat(cls, cells_x: int, cells_y: int, world_w: float, world_h: float) -> "ElevationMap":
        return cls(cells_x, cells_y, world_w, world_h,
                   heights=[[0.0] * cells_x for _ in range(cells_y)])

    def height_at(self, x: float, y: float) -> float:
        if not self.heights:
            return 0.0
        ix = int((x / self.world_w) * self.cells_x)
        iy = int((y / self.world_h) * self.cells_y)
        ix = max(0, min(self.cells_x - 1, ix))
        iy = max(0, min(self.cells_y - 1, iy))
        return self.heights[iy][ix]

    def los_blocked(self, ax: float, ay: float, bx: float, by: float) -> bool:
        """True if a higher cell sits between shooter and target along the LOS ray."""
        if not self.heights:
            return False
        ha, hb = self.height_at(ax, ay), self.height_at(bx, by)
        # Sample 20 points along the ray
        n = 20
        for i in range(1, n):
            t = i / n
            x = ax + (bx - ax) * t
            y = ay + (by - ay) * t
            line_h = ha + (hb - ha) * t + 1.5  # eye height
            if self.height_at(x, y) > line_h:
                return True
        return False


# ---------------- geometry helpers ----------------


def _segments_intersect(
    p1: tuple[float, float], p2: tuple[float, float],
    p3: tuple[float, float], p4: tuple[float, float],
) -> bool:
    """Standard segment-segment intersection test."""
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])
    return ccw(p1, p3, p4) != ccw(p2, p3, p4) and ccw(p1, p2, p3) != ccw(p1, p2, p4)


def _ray_circle_hit(
    a: tuple[float, float], b: tuple[float, float],
    cx: float, cy: float, r: float,
) -> bool:
    """Does segment a→b pass through circle (cx, cy, r)?"""
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    fx, fy = ax - cx, ay - cy
    aa = dx * dx + dy * dy
    if aa == 0:
        return (fx * fx + fy * fy) <= r * r
    bb = 2 * (fx * dx + fy * dy)
    cc = fx * fx + fy * fy - r * r
    disc = bb * bb - 4 * aa * cc
    if disc < 0:
        return False
    disc = math.sqrt(disc)
    t1 = (-bb - disc) / (2 * aa)
    t2 = (-bb + disc) / (2 * aa)
    return (0 <= t1 <= 1) or (0 <= t2 <= 1)


def los_blocked_hard(
    ax: float, ay: float, bx: float, by: float, walls: list[Wall],
) -> bool:
    """Walls fully block. Used by combat for shot resolution."""
    for w in walls:
        if _segments_intersect((ax, ay), (bx, by), w.a, w.b):
            return True
    return False


def los_blocked_soft(
    ax: float, ay: float, bx: float, by: float,
    trees: list[Tree], rng: random.Random,
) -> bool:
    """Each tree the ray crosses rolls an occlusion check."""
    for t in trees:
        if _ray_circle_hit((ax, ay), (bx, by), t.cx, t.cy, t.r):
            if rng.random() < t.occlude_chance:
                return True
    return False


def resolve_collisions(
    pos: Vec, new_pos: Vec, walls: list[Wall], trees: list[Tree], radius: float,
) -> Vec:
    """Try to move pos→new_pos; if blocked, fall back to wall-slide / tree-push."""
    # Tree push-out: keep distance r + tree.r from each tree center.
    p = Vec(new_pos)
    for t in trees:
        d = p - Vec(t.cx, t.cy)
        dist = d.length()
        min_d = t.r + radius
        if 0 < dist < min_d:
            p += d.normalize() * (min_d - dist)
        elif dist == 0:
            p += Vec(min_d, 0)
    # Wall block: if the path crosses a wall, cancel motion.
    for w in walls:
        if _segments_intersect((pos.x, pos.y), (p.x, p.y), w.a, w.b):
            return Vec(pos)  # cancel this frame's motion
    return p
