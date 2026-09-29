"""Climb from the ground floor to the attic and report the route.

The shaft carries a ladder beside the doorways rather than a stair, so this
walks to the ladder and holds up. A broken slab opening or a missing rung
shows up as a stall.

Usage: python tools/check_stairs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from gamemap import GameMap, load_tuning  # noqa: E402
from physics import Body, Physics  # noqa: E402
from playerinput import RIGHT, UP  # noqa: E402

MAX_SECONDS = 90
LADDER_CENTRE_X = 93 * 32 + 4


def room_at(game_map: GameMap, body: Body, tuning: dict) -> str | None:
    size = game_map.tile_size
    col = int((body.x + tuning["player_width"] / 2) // size)
    row = int((body.y + tuning["player_height"] / 2) // size)
    for room in game_map.rooms:
        x, y, w, h = room["rect"]
        if x <= col < x + w and y <= row < y + h:
            return room["id"]
    return None


def main() -> int:
    tuning = load_tuning()
    game_map = GameMap.load("map_01")
    physics = Physics(game_map, tuning)
    dt = 1000 / tuning["tick_hz"]

    spawn = game_map.spawn["hunter"]
    body = Body(x=float(spawn[0]), y=float(spawn[1]))

    visited: list[str] = []
    highest = body.y
    stall_ticks = 0
    tick = 0

    for tick in range(int(MAX_SECONDS * tuning["tick_hz"])):
        room = room_at(game_map, body, tuning)
        if room is not None and (not visited or visited[-1] != room):
            visited.append(room)

        # Walk to the ladder, then hold up the whole way.
        mask = RIGHT if body.x < LADDER_CENTRE_X else UP
        physics.step(body, mask, dt)

        if body.y < highest - 0.5:
            highest = body.y
            stall_ticks = 0
        else:
            stall_ticks += 1

        if room == "5F-attic" or body.y <= game_map.tile_size * 4:
            break

    ended = room_at(game_map, body, tuning)
    reached = ended in ("5F-attic", "5F-stairs")

    print("route:", " -> ".join(visited))
    print(f"ended in {ended} at y={body.y:.0f} after {tick} ticks")
    print("PASS  climbed from the ground floor to the top" if reached else "FAIL  never reached the top floor")
    return 0 if reached else 1


if __name__ == "__main__":
    raise SystemExit(main())
