"""Two-level organization: Company → Squads → Units."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pygame

from .units import Unit

Vec = pygame.math.Vector2

LEADER_DEATH_DISCIPLINE_PENALTY = 0.20
SLOT_SPACING = 12.0


@dataclass
class Squad:
    id: int
    team: str
    leader_id: int                       # id of current leader Unit
    member_ids: list[int]                # all members including leader
    company_id: int
    slot_offsets: dict[int, Vec] = field(default_factory=dict)
    goal: Vec | None = None
    objective_offset: Vec = field(default_factory=Vec)
    leader_lost: bool = False            # set when initial leader dies
    commanded_target_pos: Vec | None = None   # player override for goal-seeking
    focus_target_id: int | None = None        # player-set preferred enemy
    known_enemy_id: int | None = None
    known_enemy_pos: Vec | None = None
    known_enemy_seen_t: float = -999.0
    known_enemy_reporter_id: int | None = None


@dataclass
class Company:
    id: int
    team: str
    squad_ids: list[int]
    objective: Vec | None = None  # set by M7


def make_slot_offsets(member_ids: list[int]) -> dict[int, Vec]:
    """Lay members out in a small rectangular formation around (0,0)."""
    cols = max(1, int(math.ceil(math.sqrt(len(member_ids)))))
    offsets: dict[int, Vec] = {}
    for i, mid in enumerate(member_ids):
        r, c = divmod(i, cols)
        offsets[mid] = Vec(
            (c - (cols - 1) / 2) * SLOT_SPACING,
            (r - (len(member_ids) / cols - 1) / 2) * SLOT_SPACING,
        )
    return offsets


def apply_leader_death(squad: Squad, units_by_id: dict[int, Unit]) -> None:
    """If the leader is dead, promote the most-disciplined surviving member and
    apply a one-time discipline penalty to all members."""
    if squad.leader_lost:
        return
    leader = units_by_id.get(squad.leader_id)
    if leader is not None and leader.alive:
        return
    squad.leader_lost = True
    living = [units_by_id[mid] for mid in squad.member_ids if units_by_id[mid].alive]
    if not living:
        return
    new_leader = max(living, key=lambda u: u.discipline)
    squad.leader_id = new_leader.id
    for u in living:
        u.discipline = max(0.0, u.discipline - LEADER_DEATH_DISCIPLINE_PENALTY)


def squad_centroid(squad: Squad, units_by_id: dict[int, Unit]) -> Vec | None:
    pts = [units_by_id[mid].pos for mid in squad.member_ids if units_by_id[mid].alive]
    if not pts:
        return None
    sx = sum(p.x for p in pts) / len(pts)
    sy = sum(p.y for p in pts) / len(pts)
    return Vec(sx, sy)


def member_target(
    unit: Unit, squad: Squad, units_by_id: dict[int, Unit]
) -> Vec | None:
    """Where this member should head: leader_pos + slot_offset (when leader alive).
    If the leader is the unit itself, return the squad's goal."""
    leader = units_by_id.get(squad.leader_id)
    if leader is None or not leader.alive:
        return squad.goal
    if unit.id == squad.leader_id:
        return squad.goal
    offset = squad.slot_offsets.get(unit.id, Vec(0, 0))
    return leader.pos + offset
