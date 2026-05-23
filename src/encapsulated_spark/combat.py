"""Ranged combat: weapons, target acquisition, hit resolution."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from . import ai
from .terrain import (
    CoverPatch,
    ElevationMap,
    Tree,
    Wall,
    los_blocked_hard,
    los_blocked_soft,
)
from .units import Unit


@dataclass(frozen=True)
class WeaponSpec:
    """Musket/rifle-era ranged weapon."""
    name: str = "musket"
    range_: float = 220.0       # max effective range (world units)
    accuracy: float = 0.35      # base hit chance at point-blank vs upright target
    falloff: float = 0.6        # accuracy at max range = accuracy * falloff
    damage: float = 35.0
    reload_time: float = 2.5    # seconds between shots


DEFAULT_WEAPON = WeaponSpec()

# Shot visualization — sim records lines; renderer fades them out
SHOT_LINGER = 0.25  # seconds a shot line stays visible (in sim time)


@dataclass
class ShotEvent:
    shooter_team: str
    a: tuple[float, float]
    b: tuple[float, float]
    hit: bool
    t_emitted: float


def _pick_target(
    shooter: Unit,
    all_units: list[Unit],
    weapon: WeaponSpec,
    walls: list[Wall],
    elevation: ElevationMap | None,
    squads=None,
    units_by_id=None,
) -> Unit | None:
    """Discipline-aware target selection.

    If the shooter's squad has a player-set focus_target_id and that enemy is
    alive, in range, and visible, prefer them. Otherwise delegate to
    ai.targeting.pick. A dead focus target is cleared.
    """
    from .ai import targeting
    if (
        squads is not None
        and units_by_id is not None
        and shooter.squad_id is not None
    ):
        sq = squads.get(shooter.squad_id)
        if sq is not None and sq.focus_target_id is not None:
            enemy = units_by_id.get(sq.focus_target_id)
            if enemy is None or not enemy.alive:
                sq.focus_target_id = None
            elif targeting._visible(shooter, enemy, weapon.range_, walls, elevation):
                return enemy
            # else: focus exists but currently unreachable — fall through
            # to normal targeting so the shooter still does *something*.
    return targeting.pick(shooter, all_units, weapon.range_, walls, elevation)


def _hit_chance(
    weapon: WeaponSpec,
    distance: float,
    shooter: Unit,
    target: Unit,
    cover: list[CoverPatch],
    elevation: ElevationMap | None,
) -> float:
    """Base accuracy falls off with distance; discipline + elevation modify it;
    cover reduces effective hit chance further."""
    if distance >= weapon.range_:
        return 0.0
    t = distance / weapon.range_
    raw = weapon.accuracy * (1.0 - t * (1.0 - weapon.falloff))
    discipline_factor = 0.5 + 0.5 * shooter.discipline
    elev_bonus = 0.0
    if elevation is not None:
        sh = elevation.height_at(shooter.pos.x, shooter.pos.y)
        th = elevation.height_at(target.pos.x, target.pos.y)
        elev_bonus = max(-0.10, min(0.20, (sh - th) * 0.05))
    chance = raw * discipline_factor + elev_bonus
    # Cover doesn't reduce accuracy here — it reduces damage in _apply_damage.
    return max(0.0, min(1.0, chance))


def _damage_to(target: Unit, base: float, cover: list[CoverPatch]) -> float:
    for c in cover:
        if c.contains(target.pos):
            return base * c.damage_factor
    return base


def resolve(
    units: list[Unit],
    rng: random.Random,
    dt: float,
    sim_time: float,
    walls: list[Wall] | None = None,
    cover: list[CoverPatch] | None = None,
    trees: list[Tree] | None = None,
    elevation: ElevationMap | None = None,
    weapon: WeaponSpec = DEFAULT_WEAPON,
    squads=None,
    units_by_id=None,
) -> list[ShotEvent]:
    """Each alive unit, if cooldown elapsed and an enemy is visible & in range, fires."""
    walls = walls or []
    cover = cover or []
    trees = trees or []
    shots: list[ShotEvent] = []
    for shooter in units:
        if not shooter.alive or shooter.broken:
            continue
        if shooter.weapon_cooldown > 0.0:
            shooter.weapon_cooldown -= dt
            continue
        target = _pick_target(
            shooter, units, weapon, walls, elevation,
            squads=squads, units_by_id=units_by_id,
        )
        if target is None:
            shooter.reaction_cooldown = 0.6 * (1.0 - shooter.discipline) + 0.1
            continue
        # First-contact reaction delay (M5): unit must "wake up" before firing.
        if shooter.reaction_cooldown > 0.0:
            shooter.reaction_cooldown -= dt
            continue
        # Random-action noise: low-discipline units sometimes fire wildly.
        if rng.random() < (1.0 - shooter.discipline) * 0.04:
            # Wild shot — counts as a fired-but-miss in the log.
            shots.append(
                ShotEvent(
                    shooter_team=shooter.team,
                    a=(shooter.pos.x, shooter.pos.y),
                    b=(target.pos.x + rng.uniform(-80, 80),
                       target.pos.y + rng.uniform(-80, 80)),
                    hit=False,
                    t_emitted=sim_time,
                )
            )
            shooter.weapon_cooldown = weapon.reload_time
            continue
        # Tree (soft) occlusion: a clean LOS check might still get blocked by foliage.
        if los_blocked_soft(
            shooter.pos.x, shooter.pos.y, target.pos.x, target.pos.y, trees, rng
        ):
            # The shot is "fired into the trees" — visible miss, full cooldown.
            shots.append(
                ShotEvent(
                    shooter_team=shooter.team,
                    a=(shooter.pos.x, shooter.pos.y),
                    b=(target.pos.x, target.pos.y),
                    hit=False,
                    t_emitted=sim_time,
                )
            )
            shooter.weapon_cooldown = weapon.reload_time
            continue
        distance = (target.pos - shooter.pos).length()
        chance = _hit_chance(weapon, distance, shooter, target, cover, elevation)
        roll = rng.random()
        hit = roll < chance
        if hit:
            dmg = _damage_to(target, weapon.damage, cover)
            target.hp -= dmg
            if target.hp <= 0:
                target.alive = False
        shots.append(
            ShotEvent(
                shooter_team=shooter.team,
                a=(shooter.pos.x, shooter.pos.y),
                b=(target.pos.x, target.pos.y),
                hit=hit,
                t_emitted=sim_time,
            )
        )
        shooter.heading = math.degrees(
            math.atan2(target.pos.y - shooter.pos.y, target.pos.x - shooter.pos.x)
        )
        shooter.weapon_cooldown = weapon.reload_time
    return shots


def prune_shots(shots: list[ShotEvent], sim_time: float) -> list[ShotEvent]:
    return [s for s in shots if sim_time - s.t_emitted <= SHOT_LINGER]
