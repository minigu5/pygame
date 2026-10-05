"""Generate the one room the game is played in.

The map is a single room, walled in on every side. What the room looks like
is not the map's business: whoever opens a game room picks one of the
backgrounds listed here, and the client lays that picture over the wallpaper.

Usage: python tools/make_building_map.py [output path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TILE = 32
# Close to 16:9, so a picture covers the room with next to nothing cropped.
ROOM_WIDTH, ROOM_HEIGHT = 24, 13
WIDTH, HEIGHT = ROOM_WIDTH + 2, ROOM_HEIGHT + 2

EMPTY = 0
PALETTE = [
    {"name": "empty", "color": None, "solid": False},
    {"name": "concrete", "color": [66, 68, 76], "solid": True},
    {"name": "plank", "color": [122, 86, 58], "solid": True},
    # What shows when the chosen background has no picture on this machine.
    {"name": "wallpaper", "color": [72, 88, 116], "solid": False},
    {"name": "wallpaper-trim", "color": [53, 65, 86], "solid": False},
    {"name": "wallpaper-prop", "color": [92, 113, 148], "solid": False},
]
INDEX = {entry["name"]: number for number, entry in enumerate(PALETTE)}

# (id, display name): the backgrounds a host may choose from, the first being
# the default. The client looks for a picture named after the id in
# client/assets/rooms/.
BACKGROUNDS = [
    ("office", "사무실"),
    ("museum", "박물관"),
    ("sea", "바닷속"),
    ("cave", "동굴"),
    ("station", "기차역"),
    ("jelly", "젤리 파티"),
]


def blank() -> list[list[int]]:
    return [[EMPTY] * WIDTH for _ in range(HEIGHT)]


def fill(grid: list[list[int]], x: int, y: int, w: int, h: int, value: int) -> None:
    for row in range(y, y + h):
        for col in range(x, x + w):
            if 0 <= row < HEIGHT and 0 <= col < WIDTH:
                grid[row][col] = value


def build() -> dict:
    bg, solid, fg = blank(), blank(), blank()
    x, y, w, h = 1, 1, ROOM_WIDTH, ROOM_HEIGHT
    floor = y + h

    fill(solid, 0, 0, WIDTH, HEIGHT, INDEX["concrete"])
    fill(solid, x, y, w, h, EMPTY)
    fill(solid, x, floor, w, 1, INDEX["plank"])

    # Panelling along the bottom, a shelf and a crate: three shades to match.
    fill(bg, x, y, w, h, INDEX["wallpaper"])
    fill(bg, x, floor - 3, w, 3, INDEX["wallpaper-trim"])
    fill(bg, x + 2, floor - 5, 3, 4, INDEX["wallpaper-prop"])
    fill(bg, x + w - 5, floor - 3, 2, 2, INDEX["wallpaper-prop"])

    spawn_y = (floor - 1) * TILE
    return {
        "tile_size": TILE,
        "size": [WIDTH, HEIGHT],
        "palette": PALETTE,
        "bg": bg,
        "solid": solid,
        "fg": fg,
        "rooms": [{"id": "room", "name": "방", "floor": 1, "rect": [x, y, w, h]}],
        "backgrounds": [{"id": key, "name": name} for key, name in BACKGROUNDS],
        "spawn": {"hunter": [2 * TILE, spawn_y], "chameleon": [13 * TILE, spawn_y]},
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shared/map_01.json")
    out.write_text(json.dumps(build(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
