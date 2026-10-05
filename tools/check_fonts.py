"""Check that no label can come out as empty boxes.

A font draws a box for any character it has no glyph for. This collects every
non-ASCII character the client can put on screen (its own string literals and
the map's room names) and asks the interface font for each one.

Usage: python tools/check_fonts.py
"""

from __future__ import annotations

import ast
import json
import os
import sys
import unicodedata
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "client"))

import pygame  # noqa: E402

from fonts import has_korean, is_box, readable, ui_font  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def literals(path: Path) -> set[str]:
    """Characters of the string literals in a source file, docstrings aside."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.update(node.value)
    return found


def main() -> int:
    pygame.init()
    check("a font with Hangul is installed", has_korean())

    shown: dict[str, str] = {}      # character -> where it comes from
    for path in sorted((ROOT / "client").glob("*.py")):
        for char in literals(path):
            shown.setdefault(char, path.name)
    game_map = json.loads((ROOT / "shared" / "map_01.json").read_text(encoding="utf-8"))
    for room in game_map["rooms"]:
        for char in room["name"]:
            shown.setdefault(char, "map_01.json")

    visible = {char: source for char, source in shown.items() if ord(char) > 126 and char.isprintable()}
    check("the client has Korean labels to check", len(visible) > 50, f"{len(visible)} characters")

    font = ui_font(16)
    missing = [
        f"U+{ord(char):04X} {unicodedata.name(char, '?')} ({source})"
        for char, source in sorted(visible.items())
        if is_box(font, char)
    ]
    check("the interface font has every character the client shows", not missing, "; ".join(missing))

    # The check itself must be able to tell a box from a letter: the monospace
    # face the labels used to be drawn with has no Hangul, where it exists at all.
    mono = pygame.font.SysFont("menlo,monospace", 16)
    check(
        "and a face without Hangul is caught by this check",
        pygame.font.match_font("menlo,monospace") is None or is_box(mono, "방"),
    )
    # A room name is whatever its host typed, on whatever machine.
    check(
        "a name from outside keeps what can be shown and marks what cannot",
        readable("우리 반 Room 2￿!") == "우리 반 Room 2?!",
        readable("우리 반 Room 2￿!"),
    )

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
