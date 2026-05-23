"""Pygame rendering: units, terrain, HUD."""

from __future__ import annotations

import math

import pygame

from .input import Controls
from .sim import Sim
from .units import UNIT_RADIUS, Unit

WINDOW_SIZE = (1200, 800)
HUD_HEIGHT = 40
BG_COLOR = (30, 32, 38)
HUD_COLOR = (18, 19, 22)
RED = (220, 70, 70)
BLUE = (80, 130, 230)
WHITE = (235, 235, 235)
GREY = (140, 140, 150)

HOVER_RADIUS = 8.0
HOVER_RING_COLOR = (255, 220, 80)
INSPECTOR_BG = (15, 16, 20)
INSPECTOR_TEXT = WHITE
INSPECTOR_LINE_H = 18
INSPECTOR_FONT_SIZE = 18


def make_window() -> pygame.Surface:
    pygame.init()
    pygame.display.set_caption("Encapsulated Spark")
    return pygame.display.set_mode(WINDOW_SIZE)


def _team_color(team: str) -> tuple[int, int, int]:
    return RED if team == "red" else BLUE


def _draw_unit(
    screen: pygame.Surface, unit: Unit, y_offset: int, is_leader: bool = False
) -> None:
    color = _team_color(unit.team)
    cx, cy = int(unit.pos.x), int(unit.pos.y) + y_offset
    pygame.draw.circle(screen, color, (cx, cy), int(UNIT_RADIUS))
    if is_leader:
        pygame.draw.circle(screen, WHITE, (cx, cy), int(UNIT_RADIUS) + 2, 1)
    # heading line
    tip = (
        cx + int(math.cos(math.radians(unit.heading)) * (UNIT_RADIUS + 4)),
        cy + int(math.sin(math.radians(unit.heading)) * (UNIT_RADIUS + 4)),
    )
    pygame.draw.line(screen, color, (cx, cy), tip, 1)
    # HP ring (only when wounded — full HP = no ring, draws less clutter)
    if unit.hp < 100.0:
        frac = max(0.0, unit.hp / 100.0)
        ring_color = (int(255 * (1 - frac)), int(255 * frac), 80)
        end_angle = 2 * math.pi * frac
        pygame.draw.arc(
            screen,
            ring_color,
            (cx - UNIT_RADIUS - 2, cy - UNIT_RADIUS - 2,
             (UNIT_RADIUS + 2) * 2, (UNIT_RADIUS + 2) * 2),
            -math.pi / 2,
            -math.pi / 2 + end_angle,
            2,
        )


def _draw_shots(screen: pygame.Surface, sim: Sim, y_offset: int) -> None:
    for shot in sim.shots:
        age = sim.t - shot.t_emitted
        # fade alpha 1.0 → 0.0 across SHOT_LINGER
        from .combat import SHOT_LINGER
        alpha = max(0.0, 1.0 - age / SHOT_LINGER)
        base = (255, 240, 160) if shot.hit else (140, 140, 150)
        color = (
            int(base[0] * alpha),
            int(base[1] * alpha),
            int(base[2] * alpha),
        )
        a = (int(shot.a[0]), int(shot.a[1]) + y_offset)
        b = (int(shot.b[0]), int(shot.b[1]) + y_offset)
        pygame.draw.line(screen, color, a, b, 1)


def _draw_hud(screen: pygame.Surface, sim: Sim, controls: Controls) -> None:
    pygame.draw.rect(screen, HUD_COLOR, (0, 0, WINDOW_SIZE[0], HUD_HEIGHT))
    font = pygame.font.SysFont(None, 22)
    reds = sum(1 for u in sim.units if u.alive and u.team == "red")
    blues = sum(1 for u in sim.units if u.alive and u.team == "blue")
    line = (
        f"t={sim.t:6.1f}s   "
        f"red {reds:3d}  blue {blues:3d}   "
        f"speed {controls.label():>6}   "
        f"[space] pause  [1] 1x  [2] 4x  [3] 16x  [esc] quit"
    )
    screen.blit(font.render(line, True, WHITE), (12, 12))
    cp = sim.world.capture_point
    if cp is not None:
        from .objectives import threshold
        cap_max = threshold()
        bar_x, bar_y, bar_w, bar_h = WINDOW_SIZE[0] - 220, 14, 200, 12
        pygame.draw.rect(screen, (60, 60, 70), (bar_x, bar_y, bar_w, bar_h))
        r_frac = min(1.0, cp.meters["red"] / cap_max)
        b_frac = min(1.0, cp.meters["blue"] / cap_max)
        pygame.draw.rect(screen, RED, (bar_x, bar_y, int(bar_w * r_frac), bar_h // 2))
        pygame.draw.rect(
            screen, BLUE,
            (bar_x, bar_y + bar_h // 2, int(bar_w * b_frac), bar_h // 2),
        )


def _draw_end_screen(screen: pygame.Surface, sim: Sim) -> None:
    winner = sim.winner()
    if winner is None:
        return
    overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))
    big = pygame.font.SysFont(None, 64)
    small = pygame.font.SysFont(None, 24)
    color = RED if winner == "red" else BLUE
    title = big.render(f"{winner.upper()} wins", True, color)
    screen.blit(title, ((WINDOW_SIZE[0] - title.get_width()) // 2, 240))
    reds = [u for u in sim.units if u.team == "red"]
    blues = [u for u in sim.units if u.team == "blue"]
    r_alive = sum(1 for u in reds if u.alive)
    b_alive = sum(1 for u in blues if u.alive)
    r_broken = sum(1 for u in reds if u.broken)
    b_broken = sum(1 for u in blues if u.broken)
    lines = [
        f"time elapsed: {sim.t:.1f}s",
        f"red  alive {r_alive:3d}/{len(reds)}   broken {r_broken:3d}",
        f"blue alive {b_alive:3d}/{len(blues)}   broken {b_broken:3d}",
        "press esc to quit",
    ]
    y = 320
    for line in lines:
        surf = small.render(line, True, WHITE)
        screen.blit(surf, ((WINDOW_SIZE[0] - surf.get_width()) // 2, y))
        y += 28


WALL_COLOR = (100, 100, 110)
COVER_COLOR = (90, 100, 75)
TREE_COLOR = (50, 110, 60)
ELEV_HIGH = (90, 80, 70)
ELEV_LOW = (45, 50, 60)
OBJECTIVE_COLOR = (200, 180, 70)


def _draw_terrain(screen: pygame.Surface, sim: Sim, y_offset: int) -> None:
    world = sim.world
    # Elevation: cheap blocky shading
    if world.elevation and world.elevation.heights:
        em = world.elevation
        cell_w = WINDOW_SIZE[0] / em.cells_x
        cell_h = (WINDOW_SIZE[1] - y_offset) / em.cells_y
        max_h = max((max(row) for row in em.heights), default=0.0) or 1.0
        for iy, row in enumerate(em.heights):
            for ix, h in enumerate(row):
                if h <= 0.01:
                    continue
                frac = min(1.0, h / max_h)
                color = (
                    int(ELEV_LOW[0] + (ELEV_HIGH[0] - ELEV_LOW[0]) * frac),
                    int(ELEV_LOW[1] + (ELEV_HIGH[1] - ELEV_LOW[1]) * frac),
                    int(ELEV_LOW[2] + (ELEV_HIGH[2] - ELEV_LOW[2]) * frac),
                )
                rect = (int(ix * cell_w), int(iy * cell_h) + y_offset,
                        int(cell_w) + 1, int(cell_h) + 1)
                pygame.draw.rect(screen, color, rect)
    for c in world.cover:
        pygame.draw.rect(screen, COVER_COLOR,
                         (int(c.x), int(c.y) + y_offset, int(c.w), int(c.h)))
    for t in world.trees:
        pygame.draw.circle(screen, TREE_COLOR,
                           (int(t.cx), int(t.cy) + y_offset), int(t.r))
    for w in world.walls:
        pygame.draw.line(screen, WALL_COLOR,
                         (int(w.a[0]), int(w.a[1]) + y_offset),
                         (int(w.b[0]), int(w.b[1]) + y_offset), 3)
    if world.capture_point is not None:
        cp = world.capture_point
        pygame.draw.circle(
            screen, OBJECTIVE_COLOR,
            (int(cp.pos.x), int(cp.pos.y) + y_offset), int(cp.radius), 2,
        )


def _find_hovered_unit(sim: Sim, mouse_pos: tuple[int, int]) -> Unit | None:
    mx, my = mouse_pos
    if my < HUD_HEIGHT:
        return None
    wx, wy = mx, my - HUD_HEIGHT
    best: Unit | None = None
    best_d2 = HOVER_RADIUS * HOVER_RADIUS
    for u in sim.alive_units():
        dx = u.pos.x - wx
        dy = u.pos.y - wy
        d2 = dx * dx + dy * dy
        if d2 <= best_d2:
            best_d2 = d2
            best = u
    return best


def _draw_hover_ring(screen: pygame.Surface, unit: Unit) -> None:
    cx = int(unit.pos.x)
    cy = int(unit.pos.y) + HUD_HEIGHT
    pygame.draw.circle(
        screen, HOVER_RING_COLOR, (cx, cy), int(UNIT_RADIUS) + 4, 2
    )


def _inspector_lines(unit: Unit, sim: Sim) -> list[str]:
    is_leader = any(sq.leader_id == unit.id for sq in sim.squads.values())
    leader_tag = "  LEADER" if is_leader else ""
    squad = unit.squad_id if unit.squad_id is not None else "—"
    broken_tag = "  BROKEN" if unit.broken else ""
    target = (
        f"({unit.target_pos.x:.0f}, {unit.target_pos.y:.0f})"
        if unit.target_pos is not None else "none"
    )
    cover = (
        f"({unit.cover_waypoint.x:.0f}, {unit.cover_waypoint.y:.0f})"
        if unit.cover_waypoint is not None else "none"
    )
    return [
        f"ID       #{unit.id}   team={unit.team}   squad={squad}{leader_tag}",
        f"HP       {unit.hp:5.1f}/100   reload {unit.weapon_cooldown:4.2f}s   "
        f"react {unit.reaction_cooldown:4.2f}s",
        f"Disc     {unit.discipline:.2f}   morale {unit.morale:.2f}{broken_tag}",
        f"Pos      ({unit.pos.x:.0f}, {unit.pos.y:.0f})   "
        f"heading {unit.heading:.0f}°",
        f"Target   {target}",
        f"Cover wp {cover}",
    ]


def _draw_inspector(
    screen: pygame.Surface, unit: Unit, sim: Sim, mouse_pos: tuple[int, int]
) -> None:
    font = pygame.font.SysFont(None, INSPECTOR_FONT_SIZE)
    lines = _inspector_lines(unit, sim)
    surfs = [font.render(line, True, INSPECTOR_TEXT) for line in lines]
    panel_w = max(s.get_width() for s in surfs) + 16
    panel_h = len(surfs) * INSPECTOR_LINE_H + 12

    mx, my = mouse_pos
    px = mx + 12
    py = my + 12
    if px + panel_w > WINDOW_SIZE[0]:
        px = mx - panel_w - 12
    if py + panel_h > WINDOW_SIZE[1]:
        py = my - panel_h - 12
    px = max(0, min(WINDOW_SIZE[0] - panel_w, px))
    py = max(0, min(WINDOW_SIZE[1] - panel_h, py))

    pygame.draw.rect(screen, INSPECTOR_BG, (px, py, panel_w, panel_h))
    pygame.draw.rect(screen, _team_color(unit.team), (px, py, panel_w, panel_h), 1)
    for i, surf in enumerate(surfs):
        screen.blit(surf, (px + 8, py + 6 + i * INSPECTOR_LINE_H))


def draw_frame(screen: pygame.Surface, sim: Sim, controls: Controls) -> None:
    screen.fill(BG_COLOR)
    _draw_terrain(screen, sim, y_offset=HUD_HEIGHT)
    _draw_shots(screen, sim, y_offset=HUD_HEIGHT)
    leader_ids = {sq.leader_id for sq in sim.squads.values()}
    for unit in sim.alive_units():
        _draw_unit(
            screen, unit, y_offset=HUD_HEIGHT, is_leader=unit.id in leader_ids
        )
    _draw_hud(screen, sim, controls)
    _draw_end_screen(screen, sim)
    mouse_pos = pygame.mouse.get_pos()
    hovered = _find_hovered_unit(sim, mouse_pos)
    if hovered is not None:
        _draw_hover_ring(screen, hovered)
        _draw_inspector(screen, hovered, sim, mouse_pos)


def draw_m1_skeleton(screen: pygame.Surface) -> None:
    """Kept for the M1 smoke test."""
    screen.fill(BG_COLOR)
    w, h = screen.get_size()
    pygame.draw.circle(screen, RED, (w // 3, h // 2), 24)
    pygame.draw.circle(screen, BLUE, (2 * w // 3, h // 2), 24)
    font = pygame.font.SysFont(None, 28)
    screen.blit(font.render("red", True, WHITE), (w // 3 - 16, h // 2 + 32))
    screen.blit(font.render("blue", True, WHITE), (2 * w // 3 - 18, h // 2 + 32))
    title = font.render("Encapsulated Spark — M1 skeleton (esc to quit)", True, WHITE)
    screen.blit(title, (16, 12))
