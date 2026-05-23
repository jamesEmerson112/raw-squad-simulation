"""Keyboard input → speed control state. Mouse input → Selector."""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

SPEED_PAUSE = 0
SPEED_1X = 1
SPEED_4X = 4
SPEED_16X = 16

# Selection / command constants (kept here so input.py is self-contained;
# render.py imports HUD_HEIGHT for screen→world conversion in its own helpers).
HUD_HEIGHT = 40  # mirror of render.HUD_HEIGHT; avoids a render import cycle
DRAG_THRESHOLD_PX = 4


@dataclass
class Controls:
    speed: int = SPEED_1X
    quit: bool = False

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.quit = True
            return
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_ESCAPE, pygame.K_q):
            self.quit = True
        elif event.key == pygame.K_SPACE:
            self.speed = SPEED_PAUSE if self.speed != SPEED_PAUSE else SPEED_1X
        elif event.key == pygame.K_1:
            self.speed = SPEED_1X
        elif event.key == pygame.K_2:
            self.speed = SPEED_4X
        elif event.key == pygame.K_3:
            self.speed = SPEED_16X
        elif event.key == pygame.K_4:
            self.speed = SPEED_PAUSE

    def label(self) -> str:
        return {
            SPEED_PAUSE: "PAUSED",
            SPEED_1X: "1x",
            SPEED_4X: "4x",
            SPEED_16X: "16x",
        }[self.speed]


def _screen_to_world(pos: tuple[int, int]) -> tuple[float, float]:
    """Strip the HUD offset off a screen-space mouse position."""
    return (float(pos[0]), float(pos[1] - HUD_HEIGHT))


@dataclass
class Selector:
    """Mouse-driven squad selection + command emission.

    Selection state lives here. Issued commands are surfaced as
    `pending_command` dicts that `main.py` consumes (then sets to None).
    Move/focus-fire resolution happens in `main.py` so this stays pygame-only.
    """

    selected_squad_ids: set[int] = field(default_factory=set)
    drag_start: tuple[int, int] | None = None       # screen-space
    drag_current: tuple[int, int] | None = None     # screen-space
    pending_command: dict | None = None

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if my < HUD_HEIGHT:
                return
            self.drag_start = (mx, my)
            self.drag_current = (mx, my)
        elif event.type == pygame.MOUSEMOTION:
            if self.drag_start is not None:
                self.drag_current = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag_start is None:
                return
            sx, sy = self.drag_start
            cx, cy = self.drag_current if self.drag_current is not None else self.drag_start
            dx, dy = cx - sx, cy - sy
            moved2 = dx * dx + dy * dy
            if moved2 < DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX:
                self.pending_command = {
                    "kind": "select_click",
                    "pos": _screen_to_world((cx, cy)),
                }
            else:
                wa = _screen_to_world((sx, sy))
                wb = _screen_to_world((cx, cy))
                self.pending_command = {
                    "kind": "select_box",
                    "rect": (wa[0], wa[1], wb[0], wb[1]),
                }
            self.drag_start = None
            self.drag_current = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = event.pos
            if my < HUD_HEIGHT:
                return
            self.pending_command = {
                "kind": "command",
                "pos": _screen_to_world((mx, my)),
            }
