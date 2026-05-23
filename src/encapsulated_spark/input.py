"""Keyboard input → speed control state."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

SPEED_PAUSE = 0
SPEED_1X = 1
SPEED_4X = 4
SPEED_16X = 16


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
