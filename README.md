# Encapsulated Spark

Pygame battlefield sim where each unit's discipline drives behaviour.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Run (interactive)

```
.venv/bin/python main.py
```

Opens the setup menu. Configure, hit `enter`, watch the battle.

## Run (headless, deterministic)

```
.venv/bin/python main.py --headless --skip-setup \
  --scenario capture_the_hill --seed 42 \
  --red 80  --red-profile veteran \
  --blue 200 --blue-profile militia
```

Summary prints to stdout; event log goes to `runs/<timestamp>-<scenario>-seed<N>.jsonl`.

## In-battle keys

- `space` — pause / unpause
- `1` `2` `3` — speed 1× / 4× / 16×
- `esc` or `q` — quit

## Setup-menu keys

`↑/↓` select field · `←/→` change value · hold `shift` for bigger step · `enter` start · `esc` quit.

## Scenarios

- `two_lines` — two opposing lines, empty field
- `woods_and_wall` — partial wall, cover, trees, hill on the red side
- `capture_the_hill` — single capture-point objective in the centre

## Discipline profiles

- `militia` — mean ≈ 0.25
- `regular` — mean ≈ 0.55
- `veteran` — mean ≈ 0.85

Discipline drives accuracy, reaction time, target selection, morale, cover-seeking, contact reporting, engagement distance, and random actions.

## Tests

```
.venv/bin/python tests/test_determinism.py
.venv/bin/python tests/test_squad_freeze.py
```

## Output

Battle logs land in `runs/` (gitignored, like `.venv/`).
