"""Generate the two-floor test map used until the five-storey building lands.

Usage: python tools/make_test_map.py [output path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WIDTH, HEIGHT = 60, 32
ROOF = 8
SECOND_FLOOR = 20  # solid row that the second floor stands on
FIRST_FLOOR = 31
STAIR_X = 48

EMPTY, WOOD, STONE, BLUE, GREEN, RED = range(6)

PALETTE = [
    {"name": "empty", "color": None, "solid": False},
    {"name": "wood", "color": [139, 94, 60], "solid": True},
    {"name": "stone", "color": [70, 70, 78], "solid": True},
    {"name": "wallpaper-blue", "color": [58, 74, 110], "solid": False},
    {"name": "wallpaper-green", "color": [62, 96, 70], "solid": False},
    {"name": "carpet-red", "color": [138, 52, 58], "solid": False},
]

ROOMS = [
    {"id": "1F-lobby", "name": "로비", "floor": 1, "rect": [1, 21, 26, 10]},
    {"id": "1F-kitchen", "name": "주방", "floor": 1, "rect": [28, 21, 19, 10]},
    {"id": "2F-attic", "name": "다락방", "floor": 2, "rect": [1, 9, 46, 11]},
    {"id": "stairs", "name": "계단실", "floor": 0, "rect": [48, 9, 11, 22], "stairs": True},
]

DOORS = [
    {"a": "1F-lobby", "b": "1F-kitchen", "tile": [27, 30]},
    {"a": "1F-kitchen", "b": "stairs", "tile": [47, 30]},
    {"a": "2F-attic", "b": "stairs", "tile": [47, 19]},
]


def blank() -> list[list[int]]:
    return [[EMPTY] * WIDTH for _ in range(HEIGHT)]


def fill(grid: list[list[int]], rect: list[int], value: int) -> None:
    x, y, w, h = rect
    for row in range(y, y + h):
        for col in range(x, x + w):
            grid[row][col] = value


def build() -> dict:
    bg, solid, fg = blank(), blank(), blank()

    # Outer shell and the slab between the two floors.
    fill(solid, [0, ROOF, WIDTH, 1], STONE)
    fill(solid, [0, FIRST_FLOOR, WIDTH, 1], WOOD)
    fill(solid, [0, ROOF, 1, FIRST_FLOOR - ROOF], STONE)
    fill(solid, [WIDTH - 1, ROOF, 1, FIRST_FLOOR - ROOF], STONE)
    fill(solid, [0, SECOND_FLOOR, STAIR_X, 1], WOOD)

    # Wall between the lobby and the kitchen, with a doorway punched through.
    fill(solid, [27, 21, 1, 10], STONE)
    fill(solid, [27, 29, 1, 2], EMPTY)

    # Wall between the rooms and the staircase, open on both floors.
    fill(solid, [47, ROOF, 1, FIRST_FLOOR - ROOF], STONE)
    fill(solid, [47, 29, 1, 2], EMPTY)
    fill(solid, [47, 18, 1, 2], EMPTY)

    # Staircase: one solid step per column, climbing leftwards so that the
    # top step lands beside the second floor doorway.
    for step in range(11):
        fill(solid, [WIDTH - 2 - step, FIRST_FLOOR - 1 - step, 1, 1], WOOD)

    # Wallpaper, one colour per room.
    fill(bg, [1, 21, 26, 10], BLUE)
    fill(bg, [28, 21, 19, 10], RED)
    fill(bg, [1, 9, 46, 11], GREEN)
    fill(bg, [48, 9, 11, 22], BLUE)

    # A couple of platforms so jumping has somewhere to go.
    fill(solid, [8, 26, 5, 1], WOOD)
    fill(solid, [17, 24, 5, 1], WOOD)
    fill(solid, [33, 15, 6, 1], WOOD)

    return {
        "tile_size": 32,
        "size": [WIDTH, HEIGHT],
        "palette": PALETTE,
        "bg": bg,
        "solid": solid,
        "fg": fg,
        "rooms": ROOMS,
        "doors": DOORS,
        "spawn": {"hunter": [96, 960], "chameleon": [1120, 960]},
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shared/map_test.json")
    out.write_text(json.dumps(build(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
