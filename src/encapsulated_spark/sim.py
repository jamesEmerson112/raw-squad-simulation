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
from .terrain import los_blocked_hard, resolve_collisions
from .units import Unit
from .world import World

FIXED_DT = 1.0 / 60.0  # sim tick length in seconds
ENGAGE_HOLD_DIST = DEFAULT_WEAPON.range_ * 0.52  # slow closing after firm contact
FOLLOWER_LOCAL_HOLD_DIST = DEFAULT_WEAPON.range_ * 0.34
VISION_RANGE = DEFAULT_WEAPON.range_ * 1.05
REPORT_RANGE = 120.0
CONTACT_MEMORY_SECONDS = 4.0
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
    behavior_rng: random.Random = field(init=False)
    shots: list[ShotEvent] = field(default_factory=list)
    units_by_id: dict[int, Unit] = field(init=False)
    _ended: bool = False

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        self.behavior_rng = random.Random(self.seed ^ 0x5F3759DF)
        self.units_by_id = {u.id: u for u in self.units}
        self._seed_behavior_traits()

    def _seed_behavior_traits(self) -> None:
        for unit in self.units:
            unpredictability = 1.0 - unit.discipline
            base = ENGAGE_HOLD_DIST * (0.92 + 0.22 * unit.discipline)
            jitter = self.behavior_rng.uniform(
                -DEFAULT_WEAPON.range_ * (0.08 + 0.16 * unpredictability),
                DEFAULT_WEAPON.range_ * (0.08 + 0.16 * unpredictability),
            )
            unit.engage_hold_distance = max(
                DEFAULT_WEAPON.range_ * 0.30,
                min(DEFAULT_WEAPON.range_ * 0.76, base + jitter),
            )
            unit.next_report_t = self.behavior_rng.uniform(
                0.0, 0.8 + unpredictability
            )

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
                squad.goal = company.objective + squad.objective_offset
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
        self._update_squad_contacts(alive)
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

    def _enemy_visible_to(
        self, unit: Unit, enemy: Unit, max_range: float = VISION_RANGE
    ) -> bool:
        if enemy.team == unit.team or not enemy.alive:
            return False
        if (enemy.pos - unit.pos).length_squared() > max_range * max_range:
            return False
        if los_blocked_hard(
            unit.pos.x, unit.pos.y, enemy.pos.x, enemy.pos.y, self.world.walls
        ):
            return False
        if self.world.elevation and self.world.elevation.los_blocked(
            unit.pos.x, unit.pos.y, enemy.pos.x, enemy.pos.y
        ):
            return False
        return True

    def _nearest_visible_enemy(
        self, unit: Unit, alive: list[Unit], max_range: float = VISION_RANGE
    ) -> tuple[Unit | None, float]:
        best_unit: Unit | None = None
        best_d2 = max_range * max_range
        for other in alive:
            if not self._enemy_visible_to(unit, other, max_range):
                continue
            d2 = (other.pos - unit.pos).length_squared()
            if d2 < best_d2:
                best_d2 = d2
                best_unit = other
        if best_unit is None:
            return None, float("inf")
        return best_unit, best_d2 ** 0.5

    def _update_squad_contacts(self, alive: list[Unit]) -> None:
        """Share local sightings up to squad leaders with discipline-weighted noise."""
        for squad in self.squads.values():
            if self.t - squad.known_enemy_seen_t > CONTACT_MEMORY_SECONDS:
                squad.known_enemy_id = None
                squad.known_enemy_pos = None
                squad.known_enemy_reporter_id = None

        for unit in alive:
            if unit.broken or unit.squad_id is None or self.t < unit.next_report_t:
                continue
            unpredictability = 1.0 - unit.discipline
            unit.next_report_t = (
                self.t
                + 0.45
                + unpredictability * 1.35
                + self.behavior_rng.uniform(0.0, 0.35 + unpredictability * 0.65)
            )
            squad = self.squads.get(unit.squad_id)
            if squad is None:
                continue
            enemy, _ = self._nearest_visible_enemy(unit, alive)
            if enemy is None:
                continue

            leader = self.units_by_id.get(squad.leader_id)
            is_leader = unit.id == squad.leader_id
            in_report_range = (
                leader is not None
                and leader.alive
                and (leader.pos - unit.pos).length()
                <= REPORT_RANGE + unit.discipline * 80.0
            )
            report_chance = 0.25 + unit.discipline * 0.70
            if (
                not is_leader
                and (not in_report_range or self.behavior_rng.random() > report_chance)
            ):
                continue

            error = unpredictability * 35.0
            reported_pos = pygame.math.Vector2(enemy.pos)
            if error > 0.0:
                reported_pos += pygame.math.Vector2(
                    self.behavior_rng.uniform(-error, error),
                    self.behavior_rng.uniform(-error, error),
                )
            squad.known_enemy_id = enemy.id
            squad.known_enemy_pos = reported_pos
            squad.known_enemy_seen_t = self.t
            squad.known_enemy_reporter_id = unit.id

    def _reported_contact_distance(self, unit: Unit) -> float:
        if unit.squad_id is None:
            return float("inf")
        squad = self.squads.get(unit.squad_id)
        if (
            squad is None
            or squad.known_enemy_pos is None
            or self.t - squad.known_enemy_seen_t > CONTACT_MEMORY_SECONDS
        ):
            return float("inf")
        return (squad.known_enemy_pos - unit.pos).length()

    def _maybe_start_unpredictable_action(
        self, unit: Unit, contact_distance: float, dt: float
    ) -> None:
        if contact_distance == float("inf") or contact_distance > VISION_RANGE:
            return
        if (
            unit.hesitate_until > self.t
            or unit.wander_until > self.t
            or unit.charge_until > self.t
        ):
            return
        unpredictability = 1.0 - unit.discipline
        if self.behavior_rng.random() >= unpredictability * 0.18 * dt:
            return
        roll = self.behavior_rng.random()
        if roll < 0.36:
            unit.hesitate_until = self.t + self.behavior_rng.uniform(0.4, 1.5)
        elif roll < 0.76:
            unit.wander_until = self.t + self.behavior_rng.uniform(0.8, 2.3)
            angle = self.behavior_rng.uniform(0.0, 360.0)
            radius = self.behavior_rng.uniform(10.0, 42.0)
            unit.wander_offset = pygame.math.Vector2(radius, 0.0).rotate(angle)
        else:
            unit.charge_until = self.t + self.behavior_rng.uniform(0.7, 2.0)

    def _contact_speed_mult(self, unit: Unit, is_leader: bool) -> float:
        if unit.charge_until > self.t:
            return 1.25
        if unit.hesitate_until > self.t:
            return 0.0
        if is_leader:
            return 0.30 + (1.0 - unit.discipline) * 0.42
        return 0.45 + (1.0 - unit.discipline) * 0.25

    def _combat_goal_adjustment(
        self, unit: Unit, squad: Squad | None, contact_distance: float
    ) -> pygame.math.Vector2:
        if (
            squad is None
            or unit.cover_waypoint is not None
            or contact_distance == float("inf")
            or contact_distance > VISION_RANGE
        ):
            return pygame.math.Vector2()
        leader = self.units_by_id.get(squad.leader_id)
        leader_discipline = leader.discipline if leader is not None else unit.discipline
        unpredictability = 1.0 - leader_discipline
        squad_amp = 6.0 + unpredictability * 16.0
        squad_angle = (
            self.t * (20.0 + unpredictability * 24.0) + squad.id * 71.0
        ) % 360.0
        shift = pygame.math.Vector2(squad_amp, 0.0).rotate(squad_angle)

        personal_amp = (1.0 - unit.discipline) * 7.0
        if personal_amp > 0.0:
            personal_angle = (
                self.t * (34.0 + (1.0 - unit.discipline) * 18.0)
                + unit.id * 43.0
            ) % 360.0
            shift += pygame.math.Vector2(personal_amp, 0.0).rotate(personal_angle)
        return shift

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
        squad: Squad | None = None
        is_leader = False
        if unit.squad_id is not None and unit.squad_id in self.squads:
            squad = self.squads[unit.squad_id]
            is_leader = unit.id == squad.leader_id
            squad_goal = member_target(unit, squad, self.units_by_id)
        if squad_goal is not None:
            unit.target_pos = squad_goal
        goal = steering.current_steering_target(unit)
        if goal is None:
            return
        _, visible_dist = self._nearest_visible_enemy(unit, alive)
        reported_dist = self._reported_contact_distance(unit) if is_leader else float("inf")
        contact_dist = min(visible_dist, reported_dist)
        self._maybe_start_unpredictable_action(unit, contact_dist, dt)

        if unit.hesitate_until > self.t:
            return
        if unit.wander_until > self.t:
            goal = goal + unit.wander_offset
        goal = goal + self._combat_goal_adjustment(unit, squad, contact_dist)

        speed_mult = 1.0
        if unit.cover_waypoint is None:
            # Leaders react to squad reports. Followers only slow for immediate
            # local threats; otherwise they keep dressing on the leader.
            hold_dist = unit.engage_hold_distance or ENGAGE_HOLD_DIST
            hold_contact_dist = contact_dist if is_leader else visible_dist
            if not is_leader:
                hold_dist = min(hold_dist, FOLLOWER_LOCAL_HOLD_DIST)
            if hold_contact_dist <= hold_dist:
                speed_mult = self._contact_speed_mult(unit, is_leader)

        if unit.charge_until > self.t:
            speed_mult = max(speed_mult, 1.25)
        elif unit.wander_until > self.t:
            speed_mult = min(speed_mult, 0.65)

        self._step_toward(unit, goal, dt, speed_mult=speed_mult)

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
