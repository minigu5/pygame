"""Check the one room and the backgrounds it can wear.

The map is a single walled room; which picture hangs in it is the host's
choice among the map's backgrounds. Each of those should have a picture here,
and choosing one should change what the room looks like.

Usage: python tools/check_rooms.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import pygame  # noqa: E402

from gamemap import ROOM_ART, ROOM_ART_TYPES, GameMap  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def main() -> int:
    pygame.init()
    pygame.display.set_mode((960, 540))
    game_map = GameMap.load("map_01")

    check("the map is a single room", len(game_map.rooms) == 1, f"{len(game_map.rooms)} rooms")
    x, y, w, h = game_map.rooms[0]["rect"]
    size = game_map.tile_size
    walled = all(
        game_map.palette[game_map.solid[row][column]]["solid"]
        for row in range(y - 1, y + h + 1)
        for column in range(x - 1, x + w + 1)
        if not (x <= column < x + w and y <= row < y + h)
    )
    check("and it is walled in on every side", walled)
    spawns = {
        role: game_map.room_at(px + 12, py + 16) for role, (px, py) in game_map.spawn.items()
    }
    check("everyone spawns inside it", all(spawns.values()), str(spawns))

    ids = [entry["id"] for entry in game_map.backgrounds]
    check("the host has backgrounds to choose from", len(ids) >= 2 and len(set(ids)) == len(ids), ", ".join(ids))
    missing = [
        key for key in ids if not any((ROOM_ART / f"{key}{suffix}").is_file() for suffix in ROOM_ART_TYPES)
    ]
    check("every background has its picture", not missing, ", ".join(missing))

    # The middle of the room, as each background paints it.
    centre = ((x + w // 2) * size, (y + h // 2) * size)
    plain = tuple(game_map.world.get_at(centre))
    looks = {}
    for key in ids:
        game_map.set_background(key)
        looks[key] = pygame.image.tobytes(game_map.world, "RGB")
    check("choosing a background changes the room", len(set(looks.values())) == len(ids) - len(missing))

    game_map.set_background("no-such-background")
    check(
        "a background the map does not list leaves the wallpaper",
        tuple(game_map.world.get_at(centre)) == plain,
    )

    pygame.quit()
    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
