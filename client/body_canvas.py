"""The chameleon's painting: a small surface stamped with soft round brushes.

The canvas is laid out for the standing pose at CELLS_PER_PIXEL cells per
world pixel; body_shape maps other poses onto it. One press-to-release stroke
is one undo step. Within a stroke the stamps build up a separate layer whose
alpha is the maximum of the stamps, not their sum, so a soft edge stays soft
however slowly the cursor moves; the layer is laid over the snapshot taken at
the start of the stroke to give the visible canvas.
"""

from __future__ import annotations

import math

import pygame

from body_shape import canvas_size, extend_paint

UNDO_LIMIT = 30         # the spec asks for at least 20 steps
HARDNESS = 0.6          # share of the radius that is fully opaque; the rest fades out
STAMP_CACHE = 64

Color = tuple[int, int, int]


class BodyCanvas:
    def __init__(self, base: Color) -> None:
        self.base = base
        self.surface = pygame.Surface(canvas_size(), 0, 32)
        self.surface.fill(base)
        # Where any stamp has ever landed, so body_shape knows which cells are
        # deliberate and which still show the base colour by default.
        self.painted = pygame.Surface(canvas_size(), pygame.SRCALPHA)
        self.version = 0
        self._history: list[tuple[pygame.Surface, pygame.Surface]] = []
        self._layer: pygame.Surface | None = None
        self._stroke_open = False
        self._stamps: dict[tuple[int, int, Color], pygame.Surface] = {}
        self._extended: tuple[int, pygame.Surface] | None = None

    def begin_stroke(self) -> None:
        """Everything stamped until end_stroke comes back with one undo."""
        self._stroke_open = True
        self._layer = None

    def end_stroke(self) -> None:
        if self._layer is not None and self._history:
            # A stroke that changed nothing visible is not worth an undo step.
            before = pygame.image.tobytes(self._history[-1][0], "RGB")
            if before == pygame.image.tobytes(self.surface, "RGB"):
                self.surface, self.painted = self._history.pop()
        self._stroke_open = False
        self._layer = None

    def stamp(self, cx: float, cy: float, rx: float, ry: float, color: Color, flush: bool = True) -> None:
        """One soft ellipse of colour centred on (cx, cy), radii in cells.

        With flush=False the stamp waits in the stroke layer until flush() is
        called, so a run of stamps costs one composite.
        """
        if self._layer is None:
            self._history.append((self.surface.copy(), self.painted.copy()))
            del self._history[:-UNDO_LIMIT]
            self._layer = pygame.Surface(canvas_size(), pygame.SRCALPHA)
        brush = self._brush(max(1, round(rx)), max(1, round(ry)), color)
        self._layer.blit(
            brush,
            (round(cx) - brush.get_width() // 2, round(cy) - brush.get_height() // 2),
            special_flags=pygame.BLEND_RGBA_MAX,
        )
        if flush:
            self.flush()

    def flush(self) -> None:
        """Shows the stroke so far: the layer over the snapshot the stroke started from."""
        if self._layer is None:
            return
        snapshot, painted = self._history[-1]
        self.surface = snapshot.copy()
        self.surface.blit(self._layer, (0, 0))
        self.painted = painted.copy()
        self.painted.blit(self._layer, (0, 0))
        self.version += 1
        if not self._stroke_open:
            self._layer = None      # a bare stamp is a stroke of its own

    def line(self, start: tuple[float, float], end: tuple[float, float], rx: float, ry: float, color: Color) -> None:
        """Stamps along a segment closely enough that the stroke reads as one mark."""
        dx, dy = end[0] - start[0], end[1] - start[1]
        spacing = max(1.0, min(rx, ry) / 2)
        steps = max(1, math.ceil(math.hypot(dx, dy) / spacing))
        for step in range(steps + 1):
            t = step / steps
            self.stamp(start[0] + dx * t, start[1] + dy * t, rx, ry, color, flush=False)
        self.flush()

    def undo(self) -> bool:
        if not self._history:
            return False
        self.surface, self.painted = self._history.pop()
        self._layer = None
        self.version += 1
        return True

    @property
    def undo_depth(self) -> int:
        return len(self._history)

    def extended(self) -> pygame.Surface:
        """The canvas with unpainted cells outside the standing figure filled in
        from their neighbours, for poses that show more than standing does."""
        if self._extended is None or self._extended[0] != self.version:
            self._extended = (self.version, extend_paint(self.surface, self.painted))
        return self._extended[1]

    def _brush(self, rx: int, ry: int, color: Color) -> pygame.Surface:
        key = (rx, ry, color)
        if key not in self._stamps:
            if len(self._stamps) >= STAMP_CACHE:
                self._stamps.clear()
            self._stamps[key] = _soft_ellipse(rx, ry, color)
        return self._stamps[key]


def _soft_ellipse(rx: int, ry: int, color: Color) -> pygame.Surface:
    surface = pygame.Surface((2 * rx + 1, 2 * ry + 1), pygame.SRCALPHA)
    fade = 1.0 - HARDNESS
    for y in range(2 * ry + 1):
        for x in range(2 * rx + 1):
            distance = math.hypot((x - rx) / rx, (y - ry) / ry)
            if distance > 1.0:
                continue
            alpha = 1.0 if distance <= HARDNESS else (1.0 - distance) / fade
            surface.set_at((x, y), (*color, round(255 * alpha)))
    return surface
