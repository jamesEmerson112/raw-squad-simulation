"""Unit model and team constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pygame

Team = Literal["red", "blue"]

UNIT_RADIUS = 4.0
DEFAULT_SPEED = 30.0  # world units / sec


@dataclass
class Unit:
    id: int
    team: Team
    pos: pygame.math.Vector2
    heading: float = 0.0  # degrees; 0 = +x
    speed: float = DEFAULT_SPEED
    hp: float = 100.0
    alive: bool = True
    target_pos: pygame.math.Vector2 | None = None

    discipline: float = 0.5
    squad_id: int | None = None
    weapon_cooldown: float = 0.0

    # M5: reaction lag before engaging a newly spotted enemy
    reaction_cooldown: float = 0.0
    # M5: morale ∈ [0, 1]; broken units flee.
    morale: float = 1.0
    broken: bool = False
    # M5: cover-seeking — intermediate waypoint chosen at scenario start
    cover_waypoint: pygame.math.Vector2 | None = None

    # Tactical behavior state. Sim seeds and updates these deterministically.
    engage_hold_distance: float = 0.0
    next_report_t: float = 0.0
    hesitate_until: float = 0.0
    wander_until: float = 0.0
    charge_until: float = 0.0
    wander_offset: pygame.math.Vector2 = field(default_factory=pygame.math.Vector2)
