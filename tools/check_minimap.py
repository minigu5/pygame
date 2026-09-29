"""Render the minimap in both states and check what it does and does not show.

It runs headless, so it also serves as a guard that the map never gains a
marker for another player: the drawing code is handed no peer data at all.

Usage: python tools/check_minimap.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import pygame  # noqa: E402

from gamemap import GameMap  # noqa: E402
from minimap import ROOM_HERE, ROOM_VISITED, Minimap  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def colour_count(screen: pygame.Surface, colour: tuple[int, int, int]) -> int:
    mask = pygame.mask.from_threshold(screen, colour, (2, 2, 2, 255))
    return mask.count()


def main() -> int:
    pygame.init()
    screen = pygame.display.set_mode((960, 540))
    game_map = GameMap.load("map_01")
    minimap = Minimap(
        game_map,
        pygame.font.SysFont("menlo,monospace", 12),
        pygame.font.SysFont("applesdgothicneo,arialunicode", 13),
    )

    check(
        "every room is on the plan",
        len(game_map.rooms) == 25,
        f"{len(game_map.rooms)} rooms",
    )

    spawn = game_map.spawn["hunter"]
    position = (spawn[0] + 12.0, spawn[1] + 16.0)

    screen.fill((0, 0, 0))
    minimap.draw(screen, "1F-lobby", position, show_visited=False)
    here = colour_count(screen, ROOM_HERE)
    check("the room I am in is highlighted", here > 200, f"{here}px")
    check(
        "nothing is marked visited before I have been anywhere",
        colour_count(screen, ROOM_VISITED) == 0,
    )

    minimap.note_visit("1F-lobby")
    minimap.note_visit("1F-kitchen")
    screen.fill((0, 0, 0))
    minimap.draw(screen, "1F-store", position, show_visited=True)
    visited = colour_count(screen, ROOM_VISITED)
    check("a hunter sees the rooms it has searched", visited > 200, f"{visited}px")

    screen.fill((0, 0, 0))
    minimap.draw(screen, "1F-store", position, show_visited=False)
    check(
        "a chameleon is not shown the hunter's trail",
        colour_count(screen, ROOM_VISITED) == 0,
    )

    screen.fill((0, 0, 0))
    minimap.draw(screen, "1F-lobby", position, show_visited=False)
    compact = colour_count(screen, ROOM_HERE)
    minimap.toggle()
    screen.fill((0, 0, 0))
    minimap.draw(screen, "1F-lobby", position, show_visited=False)
    expanded = colour_count(screen, ROOM_HERE)
    check("M enlarges the plan", expanded > compact * 3, f"{compact}px -> {expanded}px")

    pygame.quit()
    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
