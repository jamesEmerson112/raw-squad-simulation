"""Pre-battle setup screen — keyboard-driven menu, returns a settings dict.

Keys
----
↑ / ↓        : move selection
← / →        : decrement / increment selected field
enter        : start battle
esc          : quit
"""

from __future__ import annotations

import pygame

from .render import BG_COLOR, BLUE, HUD_COLOR, RED, WHITE

WINDOW_SIZE = (1200, 800)
PROFILES = ("militia", "regular", "veteran")
SCENARIOS = ("two_lines", "woods_and_wall", "capture_the_hill")


def _make_window() -> pygame.Surface:
    pygame.init()
    pygame.display.set_caption("Encapsulated Spark — Setup")
    return pygame.display.set_mode(WINDOW_SIZE)


def _cycle(value, options, direction):
    idx = options.index(value)
    return options[(idx + direction) % len(options)]


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def pick_settings(defaults: dict) -> dict | None:
    """Run the setup menu. Returns settings dict, or None if user quit."""
    screen = _make_window()
    settings = dict(defaults)
    fields = [
        "scenario", "red_count", "red_profile",
        "blue_count", "blue_profile", "seed",
    ]
    selected = 0
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 48)
    body_font = pygame.font.SysFont(None, 28)
    hint_font = pygame.font.SysFont(None, 20)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return None
            if event.key == pygame.K_RETURN:
                return settings
            if event.key == pygame.K_UP:
                selected = (selected - 1) % len(fields)
            elif event.key == pygame.K_DOWN:
                selected = (selected + 1) % len(fields)
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                step = -1 if event.key == pygame.K_LEFT else 1
                shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                field_ = fields[selected]
                if field_ == "scenario":
                    settings["scenario"] = _cycle(settings["scenario"], SCENARIOS, step)
                elif field_ == "red_count":
                    settings["red_count"] = _clamp(
                        settings["red_count"] + step * (20 if shift else 5), 5, 400
                    )
                elif field_ == "blue_count":
                    settings["blue_count"] = _clamp(
                        settings["blue_count"] + step * (20 if shift else 5), 5, 400
                    )
                elif field_ == "red_profile":
                    settings["red_profile"] = _cycle(settings["red_profile"], PROFILES, step)
                elif field_ == "blue_profile":
                    settings["blue_profile"] = _cycle(settings["blue_profile"], PROFILES, step)
                elif field_ == "seed":
                    settings["seed"] = _clamp(
                        settings["seed"] + step * (10 if shift else 1), 0, 99999
                    )

        screen.fill(BG_COLOR)
        # Title
        title = title_font.render("Encapsulated Spark", True, WHITE)
        screen.blit(title, ((WINDOW_SIZE[0] - title.get_width()) // 2, 90))
        sub = body_font.render("Battlefield setup", True, (180, 180, 190))
        screen.blit(sub, ((WINDOW_SIZE[0] - sub.get_width()) // 2, 150))

        # Fields
        box = pygame.Rect(360, 220, 480, 360)
        pygame.draw.rect(screen, HUD_COLOR, box)
        rows = [
            ("Scenario", settings["scenario"]),
            ("Red units", str(settings["red_count"])),
            ("Red profile", settings["red_profile"]),
            ("Blue units", str(settings["blue_count"])),
            ("Blue profile", settings["blue_profile"]),
            ("Seed", str(settings["seed"])),
        ]
        for i, (label, value) in enumerate(rows):
            y = box.y + 24 + i * 50
            is_sel = i == selected
            arrow = "▶ " if is_sel else "  "
            label_color = WHITE if is_sel else (170, 170, 180)
            label_surf = body_font.render(arrow + label, True, label_color)
            screen.blit(label_surf, (box.x + 24, y))
            # Color the value: red/blue tinted for the matching fields
            tint = WHITE
            if label.startswith("Red"):
                tint = RED
            elif label.startswith("Blue"):
                tint = BLUE
            value_surf = body_font.render(value, True, tint)
            screen.blit(value_surf, (box.right - value_surf.get_width() - 24, y))

        hints = [
            "↑/↓: select   ←/→: change   shift+←/→: bigger step",
            "enter: start battle    esc: quit",
        ]
        for j, h in enumerate(hints):
            hs = hint_font.render(h, True, (160, 160, 170))
            screen.blit(hs, ((WINDOW_SIZE[0] - hs.get_width()) // 2, 620 + j * 22))

        pygame.display.flip()
        clock.tick(60)
