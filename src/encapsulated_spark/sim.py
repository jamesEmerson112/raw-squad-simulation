"""Deterministic simulation core. Pure — no pygame display calls here."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pygame

from .ai import morale, steering
from .combat import DEFAULT_WEAPON, ShotEvent, prune_shots, resolve
from .hierarchy import (
    Company,
    Squad,
    apply_leader_death,
    member_target,
    squad_centroid,
)
from .log import EventLog
from .terrain import resolve_collisions
from .units import Unit
from .world import World

FIXED_DT = 1.0 / 60.0  # sim tick length in seconds
ENGAGE_HOLD_DIST = DEFAULT_WEAPON.range_ * 0.85  # stop closing once near max range
FULFILL_RADIUS = 18.0   # squad centroid within this of a commanded point → done


@dataclass
class Sim:
    world: World
    units: list[Unit]
    seed: int = 0
    t: float = 0.0
    squads: dict[int, Squad] = field(default_factory=dict)
    companies: dict[int, Company] = field(default_factory=dict)
    log: EventLog = field(default_factory=EventLog)
    rng: random.Random = field(init=False)
    shots: list[ShotEvent] = field(default_factory=list)
    units_by_id: dict[int, Unit] = field(init=False)
    _ended: bool = False

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.units_by_id = {u.id: u for u in self.units}

    def alive_units(self) -> list[Unit]:
        return [u for u in self.units if u.alive]

    def step(self, dt: float = FIXED_DT) -> None:
        if self._ended:
            return
        alive_before = {u.id for u in self.alive_units()}
        broken_before = {u.id for u in self.units if u.broken}
        alive = self.alive_units()
        # Hierarchy: handle leader-death promotions and propagate company objectives.
        for squad in self.squads.values():
            prev_leader = squad.leader_id
            apply_leader_death(squad, self.units_by_id)
            if squad.leader_id != prev_leader:
                self.log.emit(
                    self.t, "leader_promoted",
                    squad_id=squad.id, team=squad.team,
                    old_leader=prev_leader, new_leader=squad.leader_id,
                )
            # Player command (move) overrides company objective. Auto-clears
            # when the squad centroid arrives within FULFILL_RADIUS.
            if squad.commanded_target_pos is not None:
                squad.goal = squad.commanded_target_pos
                c = squad_centroid(squad, self.units_by_id)
                if (
                    c is not None
                    and (c - squad.commanded_target_pos).length() < FULFILL_RADIUS
                ):
                    self.log.emit(
                        self.t, "command_fulfilled",
                        squad=squad.id, team=squad.team,
                    )
                    squad.commanded_target_pos = None
                continue
            # Squad goal = its company's objective (fallback: leader's target_pos)
            company = self.companies.get(squad.company_id)
            if company is not None and company.objective is not None:
                squad.goal = company.objective
            else:
                leader = self.units_by_id.get(squad.leader_id)
                squad.goal = (
                    leader.target_pos if leader is not None and leader.alive else squad.goal
                )
        # Morale: each team checks its own alive fraction.
        team_total = {"red": 0, "blue": 0}
        team_alive = {"red": 0, "blue": 0}
        for u in self.units:
            team_total[u.team] += 1
            if u.alive:
                team_alive[u.team] += 1
        for u in alive:
            frac = team_alive[u.team] / max(1, team_total[u.team])
            morale.update(u, frac)
        # Enemy centroid per team — used by routing units.
        centroids = self._team_centroids(alive)
        for unit in alive:
            self._advance_unit(unit, dt, alive, centroids)
        new_shots = resolve(
            self.units,
            self.rng,
            dt,
            self.t,
            walls=self.world.walls,
            cover=self.world.cover,
            trees=self.world.trees,
            elevation=self.world.elevation,
            squads=self.squads,
            units_by_id=self.units_by_id,
        )
        self.shots.extend(new_shots)
        self.shots = prune_shots(self.shots, self.t)
        # Log shots, deaths, breaks
        for s in new_shots:
            self.log.emit(self.t, "shot",
                          team=s.shooter_team, hit=s.hit,
                          a=[round(s.a[0], 2), round(s.a[1], 2)],
                          b=[round(s.b[0], 2), round(s.b[1], 2)])
        for u in self.units:
            if u.id in alive_before and not u.alive:
                self.log.emit(self.t, "death", unit=u.id, team=u.team,
                              squad=u.squad_id)
            if u.broken and u.id not in broken_before:
                self.log.emit(self.t, "broken", unit=u.id, team=u.team,
                              squad=u.squad_id)
        if self.world.capture_point is not None:
            self.world.capture_point.update(self.alive_units(), dt)
        self.t += dt
        # Match end?
        w = self.winner()
        if w is not None and not self._ended:
            self._ended = True
            self.log.emit(self.t, "match_end", winner=w)

    def winner(self) -> str | None:
        """Capture-point winner first; else team-wipeout fallback."""
        cp = self.world.capture_point
        if cp is not None and cp.winner is not None:
            return cp.winner
        red = sum(1 for u in self.units if u.alive and u.team == "red")
        blue = sum(1 for u in self.units if u.alive and u.team == "blue")
        if red == 0 and blue > 0:
            return "blue"
        if blue == 0 and red > 0:
            return "red"
        return None

    def _team_centroids(
        self, alive: list[Unit]
    ) -> dict[str, pygame.math.Vector2]:
        sums = {"red": [0.0, 0.0, 0], "blue": [0.0, 0.0, 0]}
        for u in alive:
            sums[u.team][0] += u.pos.x
            sums[u.team][1] += u.pos.y
            sums[u.team][2] += 1
        out = {}
        for team, (sx, sy, n) in sums.items():
            if n == 0:
                out[team] = pygame.math.Vector2(self.world.width / 2, self.world.height / 2)
            else:
                out[team] = pygame.math.Vector2(sx / n, sy / n)
        return out

    def _nearest_enemy_distance(self, unit: Unit, alive: list[Unit]) -> float:
        best = float("inf")
        for u in alive:
            if u.team == unit.team:
                continue
            d2 = (u.pos - unit.pos).length_squared()
            if d2 < best:
                best = d2
        return best ** 0.5

    def _advance_unit(
        self,
        unit: Unit,
        dt: float,
        alive: list[Unit],
        centroids: dict[str, pygame.math.Vector2],
    ) -> None:
        """Movement: cover waypoint → target, halt within engagement range,
        slide off walls, push out of trees. Broken units rout."""
        if unit.broken:
            enemy_centroid = centroids["blue" if unit.team == "red" else "red"]
            goal = steering.rout_target(
                unit, enemy_centroid, (self.world.width, self.world.height)
            )
            self._step_toward(unit, goal, dt, speed_mult=1.4)
            return
        # Squad-aware goal overrides individual target when a squad exists.
        squad_goal: pygame.math.Vector2 | None = None
        if unit.squad_id is not None and unit.squad_id in self.squads:
            squad_goal = member_target(unit, self.squads[unit.squad_id], self.units_by_id)
        if squad_goal is not None:
            unit.target_pos = squad_goal
        goal = steering.current_steering_target(unit)
        if goal is None:
            return
        # Stop closing once any enemy is within engagement range
        # — unless we're still routing through cover.
        if (
            unit.cover_waypoint is None
            and self._nearest_enemy_distance(unit, alive) <= ENGAGE_HOLD_DIST
        ):
            return
        self._step_toward(unit, goal, dt)

    def _step_toward(
        self,
        unit: Unit,
        goal: pygame.math.Vector2,
        dt: float,
        speed_mult: float = 1.0,
    ) -> None:
        delta = goal - unit.pos
        dist = delta.length()
        if dist < 0.5:
            return
        unit.heading = pygame.math.Vector2(1, 0).angle_to(delta)
        step = min(unit.speed * speed_mult * dt, dist)
        desired = unit.pos + delta.normalize() * step
        resolved = resolve_collisions(
            unit.pos, desired, self.world.walls, self.world.trees, radius=4.0
        )
        x, y = self.world.clamp(resolved.x, resolved.y, radius=4.0)
        unit.pos.update(x, y)
