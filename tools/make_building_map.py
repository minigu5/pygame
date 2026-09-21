"""Generate the five-storey building the game is played in.

Rooms are laid out floor by floor with a staircase shaft running the full
height on the right. Each room gets its own wallpaper so that hiding in one
means matching that room's colour rather than a single global palette.

Usage: python tools/make_building_map.py [output path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TILE = 32
WIDTH = 108
FLOOR_HEIGHT = 12      # interior rows per floor, plus one row of slab
FLOORS = 5
SHAFT_X = 92           # left edge of the stairwell shaft
LADDER_X = 92          # the ladder runs the full height of the shaft
SHAFT_WIDTH = 15
ROOF_ROW = 2
HEIGHT = ROOF_ROW + FLOORS * FLOOR_HEIGHT + 1

EMPTY = 0
PALETTE = [
    {"name": "empty", "color": None, "solid": False},
    {"name": "concrete", "color": [66, 68, 76], "solid": True},
    {"name": "plank", "color": [122, 86, 58], "solid": True},
    {"name": "lobby-tile", "color": [72, 88, 116], "solid": False},
    {"name": "kitchen-tile", "color": [126, 74, 66], "solid": False},
    {"name": "storeroom", "color": [86, 78, 62], "solid": False},
    {"name": "bedroom", "color": [96, 70, 108], "solid": False},
    {"name": "living-room", "color": [118, 104, 70], "solid": False},
    {"name": "library", "color": [64, 92, 76], "solid": False},
    {"name": "office", "color": [70, 96, 112], "solid": False},
    {"name": "washroom", "color": [96, 112, 116], "solid": False},
    {"name": "art-room", "color": [132, 96, 112], "solid": False},
    {"name": "music-room", "color": [78, 70, 122], "solid": False},
    {"name": "attic", "color": [104, 88, 66], "solid": False},
    {"name": "stairwell", "color": [58, 62, 72], "solid": False},
    {"name": "ladder", "color": [168, 132, 72], "solid": False, "ladder": True},
]
INDEX = {entry["name"]: number for number, entry in enumerate(PALETTE)}

CONCRETE, PLANK = INDEX["concrete"], INDEX["plank"]

# floor number -> rooms on it, as (id, display name, wallpaper, width in tiles)
LAYOUT: dict[int, list[tuple[str, str, str, int]]] = {
    1: [("1F-lobby", "로비", "lobby-tile", 38), ("1F-kitchen", "주방", "kitchen-tile", 30), ("1F-store", "창고", "storeroom", 22)],
    2: [("2F-bedroom", "침실", "bedroom", 42), ("2F-living", "거실", "living-room", 48)],
    3: [("3F-library", "도서관", "library", 34), ("3F-office", "사무실", "office", 34), ("3F-washroom", "화장실", "washroom", 22)],
    4: [("4F-art", "미술실", "art-room", 46), ("4F-music", "음악실", "music-room", 44)],
    5: [("5F-attic", "옥탑 다락방", "attic", 90)],
}


def blank() -> list[list[int]]:
    return [[EMPTY] * WIDTH for _ in range(HEIGHT)]


def fill(grid: list[list[int]], x: int, y: int, w: int, h: int, value: int) -> None:
    for row in range(y, y + h):
        for col in range(x, x + w):
            if 0 <= row < HEIGHT and 0 <= col < WIDTH:
                grid[row][col] = value


def floor_rows(floor: int) -> tuple[int, int]:
    """Interior top row and the solid row the floor stands on."""
    top = ROOF_ROW + (FLOORS - floor) * FLOOR_HEIGHT + 1
    return top, top + FLOOR_HEIGHT - 1


def build() -> dict:
    bg, solid, fg = blank(), blank(), blank()
    rooms: list[dict] = []
    doors: list[dict] = []

    fill(solid, 0, ROOF_ROW, WIDTH, 1, CONCRETE)
    fill(solid, 0, ROOF_ROW, 1, HEIGHT - ROOF_ROW, CONCRETE)
    fill(solid, WIDTH - 1, ROOF_ROW, 1, HEIGHT - ROOF_ROW, CONCRETE)

    for floor, entries in LAYOUT.items():
        top, slab = floor_rows(floor)
        interior = slab - top
        fill(solid, 0, slab, WIDTH, 1, PLANK)

        x = 1
        previous: str | None = None
        for room_id, name, wallpaper, width in entries:
            width = min(width, SHAFT_X - 1 - x)
            fill(bg, x, top, width, interior, INDEX[wallpaper])
            rooms.append(
                {"id": room_id, "name": name, "floor": floor, "rect": [x, top, width, interior]}
            )

            divider = x + width
            if divider < SHAFT_X:
                fill(solid, divider, top, 1, interior, CONCRETE)
                # A doorway two tiles tall, standing on the slab.
                fill(solid, divider, slab - 2, 1, 2, EMPTY)
                if previous is not None:
                    doors.append({"a": previous, "b": room_id, "tile": [divider, slab - 1]})
            previous = room_id
            x = divider + 1

        # Shaft wall, with a doorway onto every floor.
        fill(solid, SHAFT_X - 1, top, 1, interior, CONCRETE)
        fill(solid, SHAFT_X - 1, slab - 2, 1, 2, EMPTY)
        doors.append({"a": previous, "b": f"{floor}F-stairs", "tile": [SHAFT_X - 1, slab - 1]})

    # The shaft keeps a slab on every floor and a ladder runs the full height
    # beside the doorways. The slab opens only where the ladder passes, so the
    # opening sits where players climb rather than across their path.
    shaft_top, _ = floor_rows(FLOORS)
    _, shaft_bottom = floor_rows(1)
    fill(bg, SHAFT_X, shaft_top, SHAFT_WIDTH, shaft_bottom - shaft_top, INDEX["stairwell"])

    for floor in range(2, FLOORS + 1):
        _, slab = floor_rows(floor)
        fill(solid, LADDER_X, slab, 2, 1, EMPTY)

    _, ground = floor_rows(1)
    fill(fg, LADDER_X, shaft_top, 2, ground - shaft_top, INDEX["ladder"])

    for floor in range(1, FLOORS + 1):
        top, slab = floor_rows(floor)
        rooms.append(
            {
                "id": f"{floor}F-stairs",
                "name": f"{floor}층 계단실",
                "floor": floor,
                "rect": [SHAFT_X, top, SHAFT_WIDTH, slab - top],
                "stairs": True,
            }
        )

    spawn_y = (ground - 1) * TILE
    return {
        "tile_size": TILE,
        "size": [WIDTH, HEIGHT],
        "palette": PALETTE,
        "bg": bg,
        "solid": solid,
        "fg": fg,
        "rooms": rooms,
        "doors": doors,
        "spawn": {"hunter": [3 * TILE, spawn_y], "chameleon": [45 * TILE, spawn_y]},
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "shared/map_01.json")
    out.write_text(json.dumps(build(), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
