"""Draws the world slice, the players and a small status readout."""

from __future__ import annotations

from typing import Any

import pygame

from gamemap import GameMap

BACKGROUND = (12, 13, 17)
TEXT = (226, 228, 234)
OUTLINE = (16, 17, 22)


class Renderer:
    def __init__(self, screen: pygame.Surface, game_map: GameMap, tuning: dict[str, Any]) -> None:
        self.screen = screen
        self.map = game_map
        self.tuning = tuning
        self.font = pygame.font.SysFont("menlo,monospace", 16)
        self.camera = pygame.Vector2(0, 0)

    def follow(self, x: float, y: float) -> None:
        width, height = self.screen.get_size()
        self.camera.x = self._clamp(x - width / 2, 0, self.map.pixel_width - width)
        self.camera.y = self._clamp(y - height / 2, 0, self.map.pixel_height - height)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        if high < low:
            return low
        return max(low, min(high, value))

    def draw(self, me: dict[str, Any] | None, others: list[dict[str, Any]], status: list[str]) -> None:
        self.screen.fill(BACKGROUND)
        offset = (-int(self.camera.x), -int(self.camera.y))
        self.screen.blit(self.map.world, offset)

        for other in others:
            self._draw_player(other["x"], other["y"], other["c"])
        if me is not None:
            self._draw_player(me["x"], me["y"], me["c"], mark=True)

        self.screen.blit(self.map.foreground, offset)

        for index, line in enumerate(status):
            self.screen.blit(self.font.render(line, True, TEXT), (12, 10 + index * 20))

    def _draw_player(self, x: float, y: float, color: list[int], mark: bool = False) -> None:
        rect = pygame.Rect(
            int(x - self.camera.x),
            int(y - self.camera.y),
            self.tuning["player_width"],
            self.tuning["player_height"],
        )
        self.screen.fill(color, rect)
        if mark:
            pygame.draw.rect(self.screen, OUTLINE, rect, width=1)
