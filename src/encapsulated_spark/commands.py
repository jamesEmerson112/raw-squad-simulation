"""Player-issued commands: select squads, move them, focus-fire enemies.

Pure functions over `Sim`. No pygame display calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from .sim import Sim

Vec = pygame.math.Vector2


def find_squad_at(sim: "Sim", world_pos, radius: float = 8.0) -> int | None:
    """Nearest alive unit within `radius` of world_pos → its squad_id."""
    wx, wy = world_pos
    best_id: int | None = None
    best_d2 = radius * radius
    for u in sim.alive_units():
        dx = u.pos.x - wx
        dy = u.pos.y - wy
        d2 = dx * dx + dy * dy
        if d2 <= best_d2 and u.squad_id is not None:
            best_d2 = d2
            best_id = u.squad_id
    return best_id


def squads_in_rect(sim: "Sim", x0: float, y0: float, x1: float, y1: float) -> set[int]:
    """All squad_ids with >=1 alive member inside the axis-aligned rect."""
    xmin, xmax = min(x0, x1), max(x0, x1)
    ymin, ymax = min(y0, y1), max(y0, y1)
    out: set[int] = set()
    for u in sim.alive_units():
        if u.squad_id is None:
            continue
        if xmin <= u.pos.x <= xmax and ymin <= u.pos.y <= ymax:
            out.add(u.squad_id)
    return out


def find_enemy_unit_at(
    sim: "Sim", world_pos, team_to_attack: str, radius: float = 8.0
) -> int | None:
    """Nearest alive enemy unit within `radius` of world_pos. Returns unit id."""
    wx, wy = world_pos
    best_id: int | None = None
    best_d2 = radius * radius
    for u in sim.alive_units():
        if u.team == team_to_attack:
            continue
        dx = u.pos.x - wx
        dy = u.pos.y - wy
        d2 = dx * dx + dy * dy
        if d2 <= best_d2:
            best_d2 = d2
            best_id = u.id
    return best_id


def apply_move(sim: "Sim", squad_ids, world_pos) -> None:
    """Move command: sticky override of squad goal. Clears any focus-fire."""
    wx, wy = world_pos
    for sid in squad_ids:
        sq = sim.squads.get(sid)
        if sq is None:
            continue
        sq.commanded_target_pos = Vec(wx, wy)
        sq.focus_target_id = None
        sim.log.emit(
            sim.t, "command_move",
            squad=sid, team=sq.team,
            pos=[round(wx, 1), round(wy, 1)],
        )


def apply_focus_fire(sim: "Sim", squad_ids, enemy_id: int) -> None:
    """Focus-fire command: prefer this enemy when picking targets. Move goal stays."""
    enemy = sim.units_by_id.get(enemy_id)
    if enemy is None or not enemy.alive:
        return
    for sid in squad_ids:
        sq = sim.squads.get(sid)
        if sq is None or sq.team == enemy.team:
            continue
        sq.focus_target_id = enemy_id
        sim.log.emit(
            sim.t, "command_focus",
            squad=sid, team=sq.team, enemy=enemy_id,
        )


def clear_command(sim: "Sim", squad_id: int) -> None:
    sq = sim.squads.get(squad_id)
    if sq is None:
        return
    sq.commanded_target_pos = None
    sq.focus_target_id = None
