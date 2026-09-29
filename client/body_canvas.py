"""The chameleon's body as a 12x16 dot canvas, 2px per cell on a 24x32 body."""

from __future__ import annotations

import pygame

COLS, ROWS = 12, 16
UNDO_LIMIT = 30         # the spec asks for at least 20 steps

Color = tuple[int, int, int]


class BodyCanvas:
    def __init__(self, base: Color) -> None:
        self.base = base
        self.cells: list[list[Color]] = [[base] * COLS for _ in range(ROWS)]
        self._history: list[list[list[Color]]] = []
        self._stroke_open = False
        self._stroke_saved = False
        self._surface: pygame.Surface | None = None

    def begin_stroke(self) -> None:
        """Everything painted until end_stroke comes back with one undo."""
        self._stroke_open = True
        self._stroke_saved = False

    def end_stroke(self) -> None:
        self._stroke_open = False

    def paint(self, col: int, row: int, size: int, color: Color) -> bool:
        """Fills a size x size square around the cell; False when nothing changed."""
        start_col = col - (size - 1) // 2
        start_row = row - (size - 1) // 2
        targets = [
            (r, c)
            for r in range(max(0, start_row), min(ROWS, start_row + size))
            for c in range(max(0, start_col), min(COLS, start_col + size))
            if self.cells[r][c] != color
        ]
        if not targets:
            return False
        # Save the canvas only once a stroke really changes it, so hovering
        # without effect does not fill the undo history.
        if not self._stroke_open or not self._stroke_saved:
            self._history.append([list(line) for line in self.cells])
            del self._history[:-UNDO_LIMIT]
            self._stroke_saved = self._stroke_open
        for r, c in targets:
            self.cells[r][c] = color
        self._surface = None
        return True

    def undo(self) -> bool:
        if not self._history:
            return False
        self.cells = self._history.pop()
        self._stroke_saved = False
        self._surface = None
        return True

    @property
    def undo_depth(self) -> int:
        return len(self._history)

    def to_hex(self) -> str:
        """192 cells as 6-digit hex, row by row: the `g` field of the spec."""
        return "".join(f"{r:02x}{g:02x}{b:02x}" for line in self.cells for r, g, b in line)

    def surface(self) -> pygame.Surface:
        """One pixel per cell; scale it to the body with pygame.transform.scale."""
        if self._surface is None:
            self._surface = pygame.Surface((COLS, ROWS))
            for r, line in enumerate(self.cells):
                for c, color in enumerate(line):
                    self._surface.set_at((c, r), color)
        return self._surface
