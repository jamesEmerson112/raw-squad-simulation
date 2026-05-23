"""Capture-the-point objective."""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from .units import Unit

CAPTURE_THRESHOLD = 45.0          # meter target
CAPTURE_RATE_PER_NET_UNIT = 0.8   # meter / second / (red_in - blue_in)


@dataclass
class CapturePoint:
    pos: pygame.math.Vector2
    radius: float = 80.0
    meters: dict[str, float] = field(default_factory=lambda: {"red": 0.0, "blue": 0.0})
    winner: str | None = None

    def units_inside(self, units: list[Unit]) -> dict[str, int]:
        inside = {"red": 0, "blue": 0}
        r2 = self.radius * self.radius
        for u in units:
            if not u.alive or u.broken:
                continue
            if (u.pos - self.pos).length_squared() <= r2:
                inside[u.team] += 1
        return inside

    def update(self, units: list[Unit], dt: float) -> None:
        if self.winner is not None:
            return
        inside = self.units_inside(units)
        net_red = inside["red"] - inside["blue"]
        if net_red > 0:
            self.meters["red"] += CAPTURE_RATE_PER_NET_UNIT * net_red * dt
        elif net_red < 0:
            self.meters["blue"] += CAPTURE_RATE_PER_NET_UNIT * (-net_red) * dt
        if self.meters["red"] >= CAPTURE_THRESHOLD:
            self.winner = "red"
        elif self.meters["blue"] >= CAPTURE_THRESHOLD:
            self.winner = "blue"


def threshold() -> float:
    return CAPTURE_THRESHOLD
