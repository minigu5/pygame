"""Map loading and the pre-rendered layer surfaces the renderer blits from."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pygame

SHARED = Path(__file__).resolve().parent.parent / "shared"
# A picture here named after a room's id ("1F-lobby.jpg") replaces that room's wallpaper.
ROOM_ART = Path(__file__).resolve().parent / "assets" / "rooms"
ROOM_ART_TYPES = (".png", ".jpg", ".jpeg", ".webp")


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
        self._world_dim: pygame.Surface | None = None
        self._foreground: pygame.Surface | None = None
        self._art: dict[str, pygame.Surface] | None = None

    @property
    def world(self) -> pygame.Surface:
        if self._world is None:
            self._world = self._render_world()
        return self._world

    @property
    def world_dim(self) -> pygame.Surface:
        """The world as seen outside the current room: drained of colour."""
        if self._world_dim is None:
            self._world_dim = self._render_world(dim=True)
        return self._world_dim

    @property
    def foreground(self) -> pygame.Surface:
        if self._foreground is None:
            self._foreground = self._render_layers((self.fg,))
        return self._foreground

    @classmethod
    def load(cls, name: str) -> "GameMap":
        path = SHARED / f"{name}.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def room_at(self, x: float, y: float) -> str | None:
        """The room whose rect holds the world point, or None in the gaps between rooms."""
        col, row = int(x // self.tile_size), int(y // self.tile_size)
        for room in self.rooms:
            rx, ry, rw, rh = room["rect"]
            if rx <= col < rx + rw and ry <= row < ry + rh:
                return room["id"]
        return None

    def room_by_id(self, room_id: str | None) -> dict[str, Any] | None:
        if room_id is None:
            return None
        for room in self.rooms:
            if room["id"] == room_id:
                return room
        return None

    def _render_world(self, dim: bool = False) -> pygame.Surface:
        """Wallpaper, then the room pictures over it, then walls and floors on top."""
        surface = self._render_layers((self.bg,), dim=dim)
        size = self.tile_size
        for room_id, picture in self._room_art().items():
            x, y, _, _ = self.room_by_id(room_id)["rect"]
            surface.blit(_drain_picture(picture) if dim else picture, (x * size, y * size))
        return self._render_layers((self.solid,), dim=dim, onto=surface)

    def _room_art(self) -> dict[str, pygame.Surface]:
        if self._art is None:
            self._art = {}
            size = self.tile_size
            for path in sorted(ROOM_ART.glob("*")):
                room = self.room_by_id(path.stem)
                if room is None or path.suffix.lower() not in ROOM_ART_TYPES:
                    continue
                _, _, w, h = room["rect"]
                self._art[room["id"]] = _cover(pygame.image.load(str(path)), (w * size, h * size))
        return self._art

    def _render_layers(
        self,
        layers: tuple[list[list[int]], ...],
        dim: bool = False,
        onto: pygame.Surface | None = None,
    ) -> pygame.Surface:
        size = self.tile_size
        surface = onto
        if surface is None:
            surface = pygame.Surface((self.pixel_width, self.pixel_height), pygame.SRCALPHA)
        colors = [
            None if entry["color"] is None else (_drain(entry["color"], entry["solid"]) if dim else tuple(entry["color"]))
            for entry in self.palette
        ]
        for layer in layers:
            for row_index, row in enumerate(layer):
                for col_index, index in enumerate(row):
                    color = colors[index]
                    if color is None:
                        continue
                    surface.fill(
                        color,
                        pygame.Rect(col_index * size, row_index * size, size, size),
                    )
        return surface


# Outside the room the structure has to stay readable while the wallpaper
# colours do not, so walls and floors keep a brighter grey than the rest.
DIM_FACTOR = 0.45
DIM_BASE = 18
SOLID_LIFT = 58


def _drain(color: list[int], solid: bool) -> tuple[int, int, int]:
    luminance = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    value = luminance * DIM_FACTOR + DIM_BASE + (SOLID_LIFT if solid else 0)
    level = max(0, min(255, int(value)))
    return (level, level, level)


def _drain_picture(picture: pygame.Surface) -> pygame.Surface:
    """A room picture drained the way `_drain` drains a wallpaper colour."""
    grey = pygame.transform.grayscale(picture)
    factor = round(DIM_FACTOR * 255)
    grey.fill((factor, factor, factor), special_flags=pygame.BLEND_RGB_MULT)
    grey.fill((DIM_BASE, DIM_BASE, DIM_BASE), special_flags=pygame.BLEND_RGB_ADD)
    return grey


def _cover(picture: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    """Scale the picture to fill `size`, cropping around the centre whatever overflows."""
    if picture.get_bitsize() < 24:
        picture = picture.convert(24)   # smoothscale takes no palettes
    bounds = picture.get_rect()
    scale = max(size[0] / bounds.width, size[1] / bounds.height)
    crop = pygame.Rect(0, 0, round(size[0] / scale), round(size[1] / scale))
    crop.center = bounds.center
    return pygame.transform.smoothscale(picture.subsurface(crop.clip(bounds)), size)


def load_tuning() -> dict[str, Any]:
    return json.loads((SHARED / "tuning.json").read_text(encoding="utf-8"))
