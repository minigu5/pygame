"""Check that rooms look like different places.

Hiding means matching the room you stand in, so two rooms that share a
wallpaper are one hiding place wearing two names, and a room with a single
flat colour gives a hider nothing to work with.

Usage: python tools/check_rooms.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from gamemap import GameMap  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def main() -> int:
    game_map = GameMap.load("map_01")
    living = [room for room in game_map.rooms if not room.get("stairs")]

    check("the building has rooms enough to search", len(living) >= 10, f"{len(living)} rooms")

    palettes: dict[str, frozenset[int]] = {}
    thin: list[str] = []
    for room in living:
        x, y, w, h = room["rect"]
        used = Counter(
            game_map.bg[row][column]
            for row in range(y, y + h)
            for column in range(x, x + w)
        )
        palettes[room["id"]] = frozenset(index for index, count in used.items() if count >= 4)
        if len(palettes[room["id"]]) < 3:
            thin.append(f"{room['id']}({len(palettes[room['id']])})")

    check(
        "every room offers more than one shade to match",
        not thin,
        ", ".join(thin),
    )

    seen: dict[frozenset[int], str] = {}
    clashes: list[str] = []
    for room_id, palette in palettes.items():
        if palette in seen:
            clashes.append(f"{seen[palette]} = {room_id}")
        seen[palette] = room_id
    check("no two rooms are decorated alike", not clashes, ", ".join(clashes))

    colours = {
        room_id: frozenset(
            tuple(game_map.palette[index]["color"] or (0, 0, 0)) for index in palette
        )
        for room_id, palette in palettes.items()
    }
    shared = [
        f"{a} / {b}"
        for index, (a, first) in enumerate(colours.items())
        for b, second in list(colours.items())[index + 1 :]
        if first == second
    ]
    check("no two rooms share a colour scheme", not shared, ", ".join(shared))

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
