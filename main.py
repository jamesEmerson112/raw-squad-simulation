"""Entry point — launches the simulation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pygame

from encapsulated_spark import commands
from encapsulated_spark.input import Controls, Selector
from encapsulated_spark.log import EventLog, new_run_path, summarize
from encapsulated_spark.render import draw_frame, make_window
from encapsulated_spark.setup_screen import pick_settings
from encapsulated_spark.scenarios import (
    MILITIA,
    REGULAR,
    VETERAN,
    capture_the_hill,
    two_lines,
    woods_and_wall,
)
from encapsulated_spark.sim import FIXED_DT

SCENARIOS = {
    "two_lines": two_lines,
    "woods_and_wall": woods_and_wall,
    "capture_the_hill": capture_the_hill,
}
PROFILES = {"veteran": VETERAN, "regular": REGULAR, "militia": MILITIA}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Encapsulated Spark battlefield sim.")
    p.add_argument("--red", type=int, default=80, help="Red unit count")
    p.add_argument("--blue", type=int, default=80, help="Blue unit count")
    p.add_argument("--seed", type=int, default=0, help="Deterministic seed")
    p.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="woods_and_wall",
        help="Built-in scenario preset",
    )
    p.add_argument(
        "--red-profile", choices=sorted(PROFILES), default="regular",
        help="Discipline profile for red army",
    )
    p.add_argument(
        "--blue-profile", choices=sorted(PROFILES), default="regular",
        help="Discipline profile for blue army",
    )
    p.add_argument(
        "--no-log", action="store_true", help="Disable JSONL battle log"
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Run sim to completion with no window or rendering",
    )
    p.add_argument(
        "--skip-setup", action="store_true",
        help="Skip interactive setup screen; use CLI flags directly",
    )
    return p.parse_args()


def _build_sim(args: argparse.Namespace):
    log = EventLog() if args.no_log else EventLog(
        path=new_run_path(args.seed, args.scenario)
    )
    sim = SCENARIOS[args.scenario](
        red_count=args.red,
        blue_count=args.blue,
        seed=args.seed,
        red_profile=PROFILES[args.red_profile],
        blue_profile=PROFILES[args.blue_profile],
    )
    sim.log = log
    return sim


def _apply_pending_command(sim, selector: Selector) -> None:
    """Drain any pending mouse-issued command and apply it to the sim."""
    cmd = selector.pending_command
    if cmd is None:
        return
    kind = cmd["kind"]
    if kind == "select_click":
        sid = commands.find_squad_at(sim, cmd["pos"])
        selector.selected_squad_ids = {sid} if sid is not None else set()
    elif kind == "select_box":
        selector.selected_squad_ids = commands.squads_in_rect(sim, *cmd["rect"])
    elif kind == "command" and selector.selected_squad_ids:
        first_sq = next(iter(selector.selected_squad_ids))
        team = sim.squads[first_sq].team
        enemy_id = commands.find_enemy_unit_at(sim, cmd["pos"], team)
        if enemy_id is not None:
            commands.apply_focus_fire(sim, selector.selected_squad_ids, enemy_id)
        else:
            commands.apply_move(sim, selector.selected_squad_ids, cmd["pos"])
    selector.pending_command = None


def _finalize(sim) -> None:
    summary = summarize(sim)
    sim.log.emit(sim.t, "summary", **summary)
    sim.log.flush()
    print(json.dumps(summary, indent=2))


def main() -> None:
    args = parse_args()

    if not args.headless and not args.skip_setup:
        defaults = {
            "scenario": args.scenario,
            "red_count": args.red,
            "blue_count": args.blue,
            "red_profile": args.red_profile,
            "blue_profile": args.blue_profile,
            "seed": args.seed,
        }
        chosen = pick_settings(defaults)
        if chosen is None:
            pygame.quit()
            return
        args.scenario = chosen["scenario"]
        args.red = chosen["red_count"]
        args.blue = chosen["blue_count"]
        args.red_profile = chosen["red_profile"]
        args.blue_profile = chosen["blue_profile"]
        args.seed = chosen["seed"]

    sim = _build_sim(args)

    if args.headless:
        # Cap at 10 minutes of sim time to avoid runaway stalemates.
        max_ticks = int(600 / FIXED_DT)
        for _ in range(max_ticks):
            sim.step(FIXED_DT)
            if sim.winner() is not None:
                break
        _finalize(sim)
        return

    screen = make_window()
    controls = Controls()
    selector = Selector()
    clock = pygame.time.Clock()

    while not controls.quit:
        for event in pygame.event.get():
            controls.handle(event)
            selector.handle(event)

        _apply_pending_command(sim, selector)

        for _ in range(controls.speed):
            sim.step(FIXED_DT)

        draw_frame(screen, sim, controls, selector)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    _finalize(sim)


if __name__ == "__main__":
    main()
