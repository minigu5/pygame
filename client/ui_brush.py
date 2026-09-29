"""Freeze-mode brush: paints the body where it stands in the game view.

Holding the left button paints the body cells the cursor passes over; press to
release is one stroke, which one Ctrl+Z takes back. The wheel zooms the camera
in so the 12x16 cells are big enough to aim at.
"""

from __future__ import annotations

import pygame

from body_canvas import COLS, ROWS, BodyCanvas, Color

BAR_HEIGHT = 36
BAR_GAP = 8
PAD = 6
BUTTON_GAP = 6

PANEL_BG = (28, 30, 38)
PANEL_EDGE = (72, 76, 90)
LABEL = (198, 202, 212)
BUTTON = (46, 50, 62)
BUTTON_ACTIVE = (92, 132, 210)
GRID = (0, 0, 0, 60)
CURSOR = (255, 255, 255)
GRID_MIN_CELL = 6       # screen pixels per cell before the grid is worth drawing

# (label, brush size, erases)
TOOLS = (("1x1", 1, False), ("2x2", 2, False), ("4x4", 4, False), ("ERASE", 2, True))
TOOL_KEYS = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4)


class Brush:
    def __init__(self, font: pygame.font.Font, canvas: BodyCanvas) -> None:
        self.font = font
        self.canvas = canvas
        self.tool = 0
        self._buttons: list[pygame.Rect] = []
        self.pressed = False
        self._last_cell: tuple[int, int] | None = None
        self._hover: tuple[int, int] | None = None

    def select_key(self, key: int) -> bool:
        if key in TOOL_KEYS:
            self.tool = TOOL_KEYS.index(key)
            return True
        return False

    def on_mouse_down(self, pos: tuple[int, int]) -> bool:
        """Returns True when the click picked a tool."""
        for index, button in enumerate(self._buttons):
            if button.collidepoint(pos):
                self.tool = index
                return True
        return False

    def over_bar(self, pos: tuple[int, int]) -> bool:
        return any(button.collidepoint(pos) for button in self._buttons)

    def press(self, pos: tuple[int, int], body: pygame.Rect | None, color: Color) -> None:
        """Starts a stroke; it may begin off the body and be dragged onto it."""
        self.release()
        self.pressed = True
        self.canvas.begin_stroke()
        self.move(pos, body, color)

    def move(self, pos: tuple[int, int], body: pygame.Rect | None, color: Color) -> None:
        """Tracks the cursor; `body` is the body's rect on screen, None when off limits."""
        cell = None if body is None else self._cell_at(pos, body)
        self._hover = cell
        if not self.pressed or cell is None:
            # Leaving the body keeps the stroke open but must not draw a line
            # across the gap when the cursor comes back in somewhere else.
            self._last_cell = None
            return
        # A fast flick jumps several cells between events; fill the gap.
        self._paint_line(self._last_cell or cell, cell, color)
        self._last_cell = cell

    def release(self) -> None:
        """Ends the stroke: the button came up or painting stopped."""
        if self.pressed:
            self.canvas.end_stroke()
        self.pressed = False
        self._last_cell = None

    @staticmethod
    def _cell_at(pos: tuple[int, int], body: pygame.Rect) -> tuple[int, int] | None:
        if not body.collidepoint(pos):
            return None
        return (
            min(COLS - 1, (pos[0] - body.x) * COLS // body.width),
            min(ROWS - 1, (pos[1] - body.y) * ROWS // body.height),
        )

    def _paint_line(self, start: tuple[int, int], end: tuple[int, int], color: Color) -> None:
        _, size, erases = TOOLS[self.tool]
        paint = self.canvas.base if erases else color
        steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
        for step in range(steps + 1):
            col = round(start[0] + (end[0] - start[0]) * step / steps)
            row = round(start[1] + (end[1] - start[1]) * step / steps)
            self.canvas.paint(col, row, size, paint)

    def draw_bar(self, screen: pygame.Surface, below: pygame.Rect) -> None:
        """The tool buttons, in a strip just above the colour panel."""
        rect = pygame.Rect(below.x, below.y - BAR_GAP - BAR_HEIGHT, below.width, BAR_HEIGHT)
        pygame.draw.rect(screen, PANEL_BG, rect, border_radius=8)
        pygame.draw.rect(screen, PANEL_EDGE, rect, width=1, border_radius=8)
        inner = rect.width - PAD * 2
        button_w = (inner - BUTTON_GAP * (len(TOOLS) - 1)) // len(TOOLS)
        self._buttons = [
            pygame.Rect(rect.x + PAD + index * (button_w + BUTTON_GAP), rect.y + PAD, button_w, BAR_HEIGHT - PAD * 2)
            for index in range(len(TOOLS))
        ]
        for index, ((label, _, _), button) in enumerate(zip(TOOLS, self._buttons)):
            pygame.draw.rect(screen, BUTTON_ACTIVE if index == self.tool else BUTTON, button, border_radius=4)
            text = self.font.render(label, True, LABEL)
            screen.blit(text, text.get_rect(center=button.center))

    def draw_overlay(self, screen: pygame.Surface, body: pygame.Rect | None, active: bool) -> None:
        """Cell grid on the zoomed-in body, and the brush footprint under the cursor."""
        if body is None:
            return
        cell_w = body.width / COLS
        cell_h = body.height / ROWS
        if cell_w >= GRID_MIN_CELL:
            lines = pygame.Surface(body.size, pygame.SRCALPHA)
            for col in range(1, COLS):
                x = round(col * cell_w)
                pygame.draw.line(lines, GRID, (x, 0), (x, body.height))
            for row in range(1, ROWS):
                y = round(row * cell_h)
                pygame.draw.line(lines, GRID, (0, y), (body.width, y))
            screen.blit(lines, body.topleft)

        if active and self._hover is not None:
            size = TOOLS[self.tool][1]
            left = self._hover[0] - (size - 1) // 2
            top = self._hover[1] - (size - 1) // 2
            footprint = pygame.Rect(
                body.x + round(left * cell_w),
                body.y + round(top * cell_h),
                round(size * cell_w),
                round(size * cell_h),
            ).clip(body)
            pygame.draw.rect(screen, CURSOR, footprint, width=1)
