"""Battle event log (JSONL) + end-of-match stats."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EventLog:
    """Append-only event store. Flushes to disk in batches.

    Events are dicts with at minimum {'t': float, 'type': str}.
    """
    path: Path | None = None
    buffer: list[dict] = field(default_factory=list)
    flush_every: int = 200

    def emit(self, t: float, type_: str, **fields: object) -> None:
        self.buffer.append({"t": round(t, 4), "type": type_, **fields})
        if self.path is not None and len(self.buffer) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if self.path is None or not self.buffer:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for ev in self.buffer:
                f.write(json.dumps(ev) + "\n")
        self.buffer.clear()


def new_run_path(seed: int, scenario: str, runs_dir: Path = Path("runs")) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    return runs_dir / f"{ts}-{scenario}-seed{seed}.jsonl"


# ---- end-of-match stats ----

def summarize(sim) -> dict:
    """Per-team and per-squad summary of a finished (or stalled) match."""
    teams = {"red": [], "blue": []}
    for u in sim.units:
        teams[u.team].append(u)
    summary: dict = {
        "t_final": round(sim.t, 4),
        "winner": sim.winner(),
        "teams": {},
        "squads": [],
    }
    if sim.world.capture_point is not None:
        cp = sim.world.capture_point
        summary["capture_point"] = {
            "meters_red": round(cp.meters["red"], 4),
            "meters_blue": round(cp.meters["blue"], 4),
            "captured_by": cp.winner,
        }
    for team_name, members in teams.items():
        alive = sum(1 for u in members if u.alive)
        broken = sum(1 for u in members if u.broken)
        avg_disc = sum(u.discipline for u in members) / max(1, len(members))
        summary["teams"][team_name] = {
            "starting": len(members),
            "alive": alive,
            "dead": len(members) - alive,
            "broken": broken,
            "avg_discipline": round(avg_disc, 4),
        }
    for sq in sim.squads.values():
        members = [sim.units_by_id[mid] for mid in sq.member_ids]
        summary["squads"].append({
            "id": sq.id,
            "team": sq.team,
            "company_id": sq.company_id,
            "starting": len(members),
            "alive": sum(1 for u in members if u.alive),
            "leader_lost": sq.leader_lost,
        })
    return summary
