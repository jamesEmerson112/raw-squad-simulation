"""World — playfield bounds, terrain, and objectives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .objectives import CapturePoint
    from .terrain import CoverPatch, ElevationMap, Tree, Wall


@dataclass
class World:
    width: float
    height: float
    walls: list["Wall"] = field(default_factory=list)
    cover: list["CoverPatch"] = field(default_factory=list)
    trees: list["Tree"] = field(default_factory=list)
    elevation: "ElevationMap | None" = None
    capture_point: "CapturePoint | None" = None

    def clamp(self, x: float, y: float, radius: float = 0.0) -> tuple[float, float]:
        return (
            max(radius, min(self.width - radius, x)),
            max(radius, min(self.height - radius, y)),
        )
