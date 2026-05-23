"""Target selection — discipline biases toward tactical priority over nearest."""

from __future__ import annotations

from ..terrain import ElevationMap, Tree, Wall, los_blocked_hard
from ..units import Unit


def _visible(
    shooter: Unit,
    enemy: Unit,
    max_range: float,
    walls: list[Wall],
    elevation: ElevationMap | None,
) -> bool:
    if not enemy.alive:
        return False
    if (enemy.pos - shooter.pos).length_squared() > max_range * max_range:
        return False
    if los_blocked_hard(shooter.pos.x, shooter.pos.y, enemy.pos.x, enemy.pos.y, walls):
        return False
    if elevation and elevation.los_blocked(
        shooter.pos.x, shooter.pos.y, enemy.pos.x, enemy.pos.y
    ):
        return False
    return True


def pick(
    shooter: Unit,
    all_units: list[Unit],
    max_range: float,
    walls: list[Wall],
    elevation: ElevationMap | None,
) -> Unit | None:
    """Score candidates and pick the highest-scoring visible enemy in range.

    Score blends:
      - inverse-distance (always positive)
      - inverse-HP (finish-off bonus) weighted by discipline
      - "wounded > healthy" bias only kicks in for disciplined shooters
    """
    discipline = shooter.discipline
    best: Unit | None = None
    best_score = float("-inf")
    for enemy in all_units:
        if enemy.team == shooter.team:
            continue
        if not _visible(shooter, enemy, max_range, walls, elevation):
            continue
        dist = (enemy.pos - shooter.pos).length()
        proximity_score = 1.0 - (dist / max_range)
        finishoff_bonus = discipline * (1.0 - enemy.hp / 100.0)
        broken_target_bonus = discipline * 0.15 if enemy.broken else 0.0
        score = proximity_score + finishoff_bonus + broken_target_bonus
        if score > best_score:
            best_score = score
            best = enemy
    return best
