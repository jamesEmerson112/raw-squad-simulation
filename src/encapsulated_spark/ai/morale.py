"""Morale: low discipline → low panic threshold → unit breaks earlier."""

from __future__ import annotations

from ..units import Unit

# Below this team-strength fraction, the unit starts checking for panic.
BASE_PANIC_THRESHOLD = 0.55
# Once broken, units stay broken (no rally in M5).


def update(unit: Unit, team_alive_frac: float) -> None:
    """Update morale and broken state for a single unit, in place."""
    if unit.broken:
        return
    # Effective threshold rises with discipline (more disciplined → tolerates more loss).
    # discipline=1.0 → threshold 0.35, discipline=0.0 → threshold 0.75
    threshold = BASE_PANIC_THRESHOLD - 0.20 * unit.discipline + 0.20 * (1 - unit.discipline)
    if team_alive_frac < threshold:
        # decay morale faster when team strength is lower
        deficit = threshold - team_alive_frac
        unit.morale = max(0.0, unit.morale - 0.01 * deficit)
        # break when morale hits zero
        if unit.morale <= 0.001:
            unit.broken = True
