"""Built-in scenario presets."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .ai import steering
from .hierarchy import Company, Squad, make_slot_offsets
from .objectives import CapturePoint
from .sim import Sim
from .terrain import CoverPatch, ElevationMap, Tree, Wall
from .units import Unit
from .world import World

SQUAD_SIZE = 8
SQUADS_PER_COMPANY = 5

PLAYFIELD = (1200.0, 760.0)  # leaves room for HUD strip at top


@dataclass(frozen=True)
class DisciplineProfile:
    mean: float
    stddev: float


VETERAN = DisciplineProfile(mean=0.85, stddev=0.08)
REGULAR = DisciplineProfile(mean=0.55, stddev=0.12)
MILITIA = DisciplineProfile(mean=0.25, stddev=0.15)


def _sample_discipline(profile: DisciplineProfile, rng: random.Random) -> float:
    return max(0.0, min(1.0, rng.gauss(profile.mean, profile.stddev)))


def two_lines(
    red_count: int = 80,
    blue_count: int = 80,
    seed: int = 0,
    red_profile: DisciplineProfile = REGULAR,
    blue_profile: DisciplineProfile = REGULAR,
) -> Sim:
    """Two parallel lines facing each other, each unit heading for the opposite line."""
    world = World(width=PLAYFIELD[0], height=PLAYFIELD[1])
    rng = random.Random(seed)
    units: list[Unit] = []
    uid = 0

    def line(team: str, x: float, count: int, target_x: float,
             profile: DisciplineProfile) -> None:
        nonlocal uid
        spacing = world.height / (count + 1)
        for i in range(count):
            y = spacing * (i + 1) + rng.uniform(-2.0, 2.0)
            pos = pygame.math.Vector2(x + rng.uniform(-2.0, 2.0), y)
            target = pygame.math.Vector2(target_x, y)
            units.append(
                Unit(
                    id=uid,
                    team=team,  # type: ignore[arg-type]
                    pos=pos,
                    heading=0.0 if team == "red" else 180.0,
                    target_pos=target,
                    discipline=_sample_discipline(profile, rng),
                )
            )
            uid += 1

    line("red", x=120.0, count=red_count, target_x=world.width - 120.0,
         profile=red_profile)
    line("blue", x=world.width - 120.0, count=blue_count, target_x=120.0,
         profile=blue_profile)
    sim = Sim(world=world, units=units, seed=seed)
    _organize_into_squads(sim)
    return sim


def _organize_into_squads(sim: Sim) -> None:
    """Group each team's units into squads of SQUAD_SIZE, and companies of
    SQUADS_PER_COMPANY. The most-disciplined unit per squad becomes the leader."""
    sid = 0
    cid = 0
    for team in ("red", "blue"):
        team_units = [u for u in sim.units if u.team == team]
        # Chunk into squads
        team_squad_ids: list[int] = []
        for i in range(0, len(team_units), SQUAD_SIZE):
            chunk = team_units[i:i + SQUAD_SIZE]
            if not chunk:
                continue
            leader = max(chunk, key=lambda u: u.discipline)
            member_ids = [u.id for u in chunk]
            squad = Squad(
                id=sid,
                team=team,
                leader_id=leader.id,
                member_ids=member_ids,
                company_id=-1,  # filled below
                slot_offsets=make_slot_offsets(member_ids),
            )
            for u in chunk:
                u.squad_id = sid
            sim.squads[sid] = squad
            team_squad_ids.append(sid)
            sid += 1
        # Group squads into companies
        for j in range(0, len(team_squad_ids), SQUADS_PER_COMPANY):
            comp_squad_ids = team_squad_ids[j:j + SQUADS_PER_COMPANY]
            company = Company(id=cid, team=team, squad_ids=comp_squad_ids)
            for s_id in comp_squad_ids:
                sim.squads[s_id].company_id = cid
            sim.companies[cid] = company
            cid += 1


def woods_and_wall(
    red_count: int = 80,
    blue_count: int = 80,
    seed: int = 0,
    red_profile: DisciplineProfile = REGULAR,
    blue_profile: DisciplineProfile = REGULAR,
) -> Sim:
    """Two-lines scenario with a partial wall, cover patches near each spawn,
    a tree line in the middle, and a small hill for the red team."""
    sim = two_lines(
        red_count=red_count, blue_count=blue_count, seed=seed,
        red_profile=red_profile, blue_profile=blue_profile,
    )
    w = sim.world
    rng = random.Random(seed ^ 0xBEEF)
    # Wall: vertical segment in the middle, gap in the center
    cx, cy = w.width / 2, w.height / 2
    w.walls.append(Wall(a=(cx, 40.0), b=(cx, cy - 80.0)))
    w.walls.append(Wall(a=(cx, cy + 80.0), b=(cx, w.height - 40.0)))
    # Cover near each spawn
    w.cover.append(CoverPatch(x=180.0, y=cy - 40.0, w=40.0, h=80.0))
    w.cover.append(CoverPatch(x=w.width - 220.0, y=cy - 40.0, w=40.0, h=80.0))
    # Trees scattered in middle band (avoid spawn cols)
    for _ in range(18):
        tx = rng.uniform(w.width * 0.30, w.width * 0.70)
        ty = rng.uniform(40.0, w.height - 40.0)
        w.trees.append(Tree(cx=tx, cy=ty, r=rng.uniform(8.0, 14.0)))
    # Elevation: small hill on the red (left) side
    em = ElevationMap.flat(cells_x=24, cells_y=16, world_w=w.width, world_h=w.height)
    hill_cx, hill_cy = 6, 8
    for iy in range(em.cells_y):
        for ix in range(em.cells_x):
            d = math.hypot(ix - hill_cx, iy - hill_cy)
            em.heights[iy][ix] = max(0.0, 3.0 - d * 0.7)
    w.elevation = em
    # Now that cover exists, assign per-unit cover waypoints (M5).
    wp_rng = random.Random(seed ^ 0xC0FE)
    for unit in sim.units:
        steering.assign_cover_waypoint(unit, w.cover, wp_rng)
    return sim


def capture_the_hill(
    red_count: int = 80,
    blue_count: int = 80,
    seed: int = 0,
    red_profile: DisciplineProfile = REGULAR,
    blue_profile: DisciplineProfile = REGULAR,
) -> Sim:
    """Single capture point in the center; both armies advance on it.
    First team to fill the capture meter wins."""
    sim = two_lines(
        red_count=red_count, blue_count=blue_count, seed=seed,
        red_profile=red_profile, blue_profile=blue_profile,
    )
    w = sim.world
    cx, cy = w.width / 2, w.height / 2
    w.capture_point = CapturePoint(pos=pygame.math.Vector2(cx, cy), radius=80.0)
    # Override company objectives so squads converge on the point.
    point = pygame.math.Vector2(cx, cy)
    for comp in sim.companies.values():
        comp.objective = point
    for team in ("red", "blue"):
        squad_ids = sorted(sid for sid, sq in sim.squads.items() if sq.team == team)
        if not squad_ids:
            continue
        team_side = -1.0 if team == "red" else 1.0
        mid = (len(squad_ids) - 1) / 2
        for i, sid in enumerate(squad_ids):
            lateral = (i - mid) * 24.0
            sim.squads[sid].objective_offset = pygame.math.Vector2(
                team_side * 18.0, lateral
            )
    # Add light cover flanking the objective.
    w.cover.append(CoverPatch(x=cx - 160.0, y=cy + 90.0, w=50.0, h=20.0))
    w.cover.append(CoverPatch(x=cx + 110.0, y=cy - 110.0, w=50.0, h=20.0))
    return sim
