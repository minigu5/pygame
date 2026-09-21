"""Map loading and the pre-rendered layer surfaces the renderer blits from."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pygame

SHARED = Path(__file__).resolve().parent.parent / "shared"


class GameMap:
    def __init__(self, data: dict[str, Any]) -> None:
        self.tile_size: int = data["tile_size"]
        self.width, self.height = data["size"]
        self.palette: list[dict[str, Any]] = data["palette"]
        self.bg: list[list[int]] = data["bg"]
        self.solid: list[list[int]] = data["solid"]
        self.fg: list[list[int]] = data["fg"]
        self.rooms: list[dict[str, Any]] = data["rooms"]
        self.spawn: dict[str, list[int]] = data["spawn"]

        self.pixel_width = self.width * self.tile_size
        self.pixel_height = self.height * self.tile_size

        # Built on first use so that physics-only callers need no video mode.
        self._world: pygame.Surface | None = None
        self._foreground: pygame.Surface | None = None

    @property
    def world(self) -> pygame.Surface:
        if self._world is None:
            self._world = self._render_layers((self.bg, self.solid))
        return self._world

    @property
    def foreground(self) -> pygame.Surface:
        if self._foreground is None:
            self._foreground = self._render_layers((self.fg,))
        return self._foreground

    @classmethod
    def load(cls, name: str) -> "GameMap":
        path = SHARED / f"{name}.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def room_by_id(self, room_id: str | None) -> dict[str, Any] | None:
        if room_id is None:
            return None
        for room in self.rooms:
            if room["id"] == room_id:
                return room
        return None

    def _render_layers(self, layers: tuple[list[list[int]], ...]) -> pygame.Surface:
        size = self.tile_size
        surface = pygame.Surface((self.pixel_width, self.pixel_height), pygame.SRCALPHA)
        for layer in layers:
            for row_index, row in enumerate(layer):
                for col_index, index in enumerate(row):
                    color = self.palette[index]["color"]
                    if color is None:
                        continue
                    surface.fill(
                        color,
                        pygame.Rect(col_index * size, row_index * size, size, size),
                    )
        return surface


def load_tuning() -> dict[str, Any]:
    return json.loads((SHARED / "tuning.json").read_text(encoding="utf-8"))
