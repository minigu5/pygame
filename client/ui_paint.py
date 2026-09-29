"""Freeze-mode painting: HSB sliders, an eyedropper mode and a preview."""

from __future__ import annotations

from typing import Any

import pygame

PANEL_WIDTH = 220
PANEL_MARGIN = 16
ROW_HEIGHT = 46
TRACK_HEIGHT = 10
HANDLE_WIDTH = 8

PANEL_BG = (28, 30, 38)
PANEL_EDGE = (72, 76, 90)
LABEL = (198, 202, 212)
HINT = (140, 145, 158)
TRACK = (58, 62, 74)
HANDLE = (232, 234, 240)

CHANNELS = (("H", 360), ("S", 100), ("B", 100))


def rgb_to_hsb(color: tuple[int, int, int]) -> list[float]:
    h, s, v, _ = pygame.Color(*color).hsva
    return [h, s, v]


def hsb_to_rgb(hsb: list[float]) -> tuple[int, int, int]:
    color = pygame.Color(0)
    color.hsva = (hsb[0] % 360, max(0.0, min(100.0, hsb[1])), max(0.0, min(100.0, hsb[2])), 100.0)
    return (color.r, color.g, color.b)


class PaintPanel:
    """Edits one colour. Open only while the player is frozen."""

    def __init__(self, font: pygame.font.Font, color: tuple[int, int, int]) -> None:
        self.font = font
        self.hsb = rgb_to_hsb(color)
        self.eyedropper = False
        self.dragging: int | None = None
        self._rows: list[pygame.Rect] = []
        self._dirty = False

    @property
    def color(self) -> tuple[int, int, int]:
        return hsb_to_rgb(self.hsb)

    def set_color(self, color: tuple[int, int, int]) -> None:
        self.hsb = rgb_to_hsb(color)
        self._dirty = True

    def take_change(self) -> tuple[int, int, int] | None:
        """Returns the colour once after it settles, for sending to the server."""
        if not self._dirty or self.dragging is not None:
            return None
        self._dirty = False
        return self.color

    def toggle_eyedropper(self) -> None:
        self.eyedropper = not self.eyedropper

    def layout(self, screen: pygame.Surface) -> pygame.Rect:
        height = ROW_HEIGHT * len(CHANNELS) + 96
        rect = pygame.Rect(
            screen.get_width() - PANEL_WIDTH - PANEL_MARGIN,
            screen.get_height() - height - PANEL_MARGIN,
            PANEL_WIDTH,
            height,
        )
        self._rows = [
            pygame.Rect(rect.x + 16, rect.y + 60 + index * ROW_HEIGHT + 22, PANEL_WIDTH - 32, TRACK_HEIGHT)
            for index in range(len(CHANNELS))
        ]
        return rect

    def on_mouse_down(self, pos: tuple[int, int]) -> bool:
        """Returns True when the click belongs to the panel."""
        for index, track in enumerate(self._rows):
            if track.inflate(0, 16).collidepoint(pos):
                self.dragging = index
                self._apply(index, pos[0])
                return True
        return False

    def on_mouse_up(self) -> None:
        self.dragging = None

    def on_mouse_move(self, pos: tuple[int, int]) -> None:
        if self.dragging is not None:
            self._apply(self.dragging, pos[0])

    def _apply(self, index: int, mouse_x: int) -> None:
        track = self._rows[index]
        ratio = (mouse_x - track.x) / max(1, track.width)
        self.hsb[index] = max(0.0, min(1.0, ratio)) * CHANNELS[index][1]
        self._dirty = True

    def draw(self, screen: pygame.Surface) -> None:
        rect = self.layout(screen)
        pygame.draw.rect(screen, PANEL_BG, rect, border_radius=8)
        pygame.draw.rect(screen, PANEL_EDGE, rect, width=1, border_radius=8)

        swatch = pygame.Rect(rect.x + 16, rect.y + 16, 48, 32)
        pygame.draw.rect(screen, self.color, swatch, border_radius=4)
        pygame.draw.rect(screen, PANEL_EDGE, swatch, width=1, border_radius=4)

        red, green, blue = self.color
        screen.blit(self.font.render(f"{red:3d} {green:3d} {blue:3d}", True, LABEL), (rect.x + 76, rect.y + 24))

        for index, ((name, maximum), track) in enumerate(zip(CHANNELS, self._rows)):
            value = self.hsb[index]
            screen.blit(
                self.font.render(f"{name} {value:5.1f}", True, LABEL),
                (track.x, track.y - 20),
            )
            pygame.draw.rect(screen, TRACK, track, border_radius=5)
            handle_x = track.x + int(track.width * (value / maximum)) - HANDLE_WIDTH // 2
            pygame.draw.rect(
                screen,
                HANDLE,
                pygame.Rect(handle_x, track.y - 4, HANDLE_WIDTH, TRACK_HEIGHT + 8),
                border_radius=3,
            )

        hint = "eyedropper ON - click the map" if self.eyedropper else "E  eyedropper"
        screen.blit(self.font.render(hint, True, HINT), (rect.x + 16, rect.bottom - 26))


def sample_map_color(game_map: Any, world_x: float, world_y: float) -> tuple[int, int, int] | None:
    """Reads the map's own colour, never the screen, so players and UI cannot bleed in."""
    if not (0 <= world_x < game_map.pixel_width and 0 <= world_y < game_map.pixel_height):
        return None
    red, green, blue, alpha = game_map.world.get_at((int(world_x), int(world_y)))
    if alpha == 0:
        return None
    return (red, green, blue)
