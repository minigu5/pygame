"""Freeze-mode brush: paints the body where it stands in the game view.

Holding the left button paints wherever the cursor passes over the body;
press to release is one stroke, which one Ctrl+Z takes back. The wheel zooms
the camera in so the body is big enough to paint on. The stroke is walked in
the pose's own cell grid and every stamp is mapped onto the one standing
canvas by body_shape, so it lands where the cursor shows it in any pose.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import body_shape
from body_canvas import BodyCanvas, Color
from ui_bar import ButtonBar

CURSOR = (255, 255, 255)
CURSOR_SHADOW = (0, 0, 0)
MIN_CURSOR_PX = 2

# (label, ASCII label for machines without a Korean font, radius in canvas cells, erases)
TOOLS = (
    ("가늘게", "thin", 3, False),
    ("보통", "mid", 7, False),
    ("굵게", "thick", 14, False),
    ("지우개", "erase", 10, True),
)
TOOL_KEYS = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4)


@dataclass
class PaintTarget:
    """The body as drawn this frame: its screen rect and the pose it is in."""

    rect: pygame.Rect
    pose: str

    def cell_at(self, pos: tuple[int, int]) -> tuple[float, float] | None:
        """The cursor as a point in the pose's cell grid, or None when off the body."""
        if not self.rect.collidepoint(pos):
            return None
        cells_w, cells_h = body_shape.cell_size(self.pose)
        return (
            (pos[0] - self.rect.x) * cells_w / self.rect.width,
            (pos[1] - self.rect.y) * cells_h / self.rect.height,
        )

    def cell_px(self) -> float:
        """Screen pixels per canvas cell."""
        return self.rect.width / body_shape.cell_size(self.pose)[0]


class Brush:
    def __init__(self, font: pygame.font.Font, canvas: BodyCanvas, ascii_labels: bool = False) -> None:
        self.canvas = canvas
        self.bar = ButtonBar(font, [tool[1] if ascii_labels else tool[0] for tool in TOOLS], TOOL_KEYS)
        self.pressed = False
        self._last: tuple[float, float] | None = None     # last stamp, in the pose's cells
        self._last_pose: str | None = None
        self._hover: tuple[int, int] | None = None         # cursor on screen when over the body
        self._stamped = False                              # paint went down since take_stamped()

    @property
    def tool(self) -> int:
        return self.bar.selected

    def press(self, pos: tuple[int, int], target: PaintTarget | None, color: Color) -> None:
        """Starts a stroke; it may begin off the body and be dragged onto it."""
        self.release()
        self.pressed = True
        self.canvas.begin_stroke()
        self.move(pos, target, color)

    def move(self, pos: tuple[int, int], target: PaintTarget | None, color: Color) -> None:
        """Tracks the cursor; `target` is None when painting is not allowed there."""
        cell = None if target is None else target.cell_at(pos)
        self._hover = pos if cell is not None else None
        if not self.pressed or cell is None or target is None:
            # Leaving the body keeps the stroke open but must not draw a line
            # across the gap when the cursor comes back in somewhere else.
            self._last = None
            return
        if target.pose != self._last_pose:
            # The body changed shape under the cursor: the old point means nothing now.
            self._last = None
            self._last_pose = target.pose
        _, _, radius, erases = TOOLS[self.tool]
        paint = self.canvas.base if erases else color
        self._walk(self._last or cell, cell, target.pose, radius, paint)
        self._last = cell
        self._stamped = True

    def take_stamped(self) -> bool:
        """True once after paint has gone down, so the caller can sound the brush."""
        stamped, self._stamped = self._stamped, False
        return stamped

    def lift(self) -> None:
        """Breaks the line without ending the stroke, e.g. when the view changes
        under the cursor and the next point is somewhere else on the body."""
        self._last = None

    def release(self) -> None:
        """Ends the stroke: the button came up or painting stopped."""
        if self.pressed:
            self.canvas.end_stroke()
        self.pressed = False
        self._last = None

    def _walk(self, start: tuple[float, float], end: tuple[float, float], pose: str, radius: float, color: Color) -> None:
        """Stamps along a segment of the pose's grid closely enough to read as one mark."""
        dx, dy = end[0] - start[0], end[1] - start[1]
        steps = max(1, math.ceil(math.hypot(dx, dy) / max(1.0, radius / 2)))
        for step in range(steps + 1):
            t = step / steps
            cx, cy, rx, ry = body_shape.stamp_geometry(pose, start[0] + dx * t, start[1] + dy * t, radius)
            self.canvas.stamp(cx, cy, rx, ry, color, flush=False)
        self.canvas.flush()

    def draw_cursor(self, screen: pygame.Surface, target: PaintTarget | None) -> None:
        """The brush's footprint under the cursor while it is over the body."""
        if target is None or self._hover is None:
            return
        radius = max(MIN_CURSOR_PX, round(TOOLS[self.tool][2] * target.cell_px()))
        pygame.draw.circle(screen, CURSOR_SHADOW, self._hover, radius + 1, width=1)
        pygame.draw.circle(screen, CURSOR, self._hover, radius, width=1)
