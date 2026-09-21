"""Room-framed camera: the current room fills the middle of the screen and
everything beyond it is drained to grey."""

from __future__ import annotations

from typing import Any

import pygame

from gamemap import GameMap

BACKGROUND = (10, 11, 15)
TEXT = (226, 228, 234)
OUTLINE = (16, 17, 22)

ROOM_FILL = 0.70        # share of the screen the room should occupy
MIN_SCALE, MAX_SCALE = 0.5, 2.0
EASE = 0.18             # per frame, so a room change settles in ~0.2s


class Renderer:
    def __init__(self, screen: pygame.Surface, game_map: GameMap, tuning: dict[str, Any]) -> None:
        self.screen = screen
        self.map = game_map
        self.tuning = tuning
        self.font = pygame.font.SysFont("menlo,monospace", 16)
        self.camera = pygame.Vector2(0, 0)
        self.scale = 1.0
        self._settled = False

    def frame(self, room_id: str | None, focus_x: float, focus_y: float) -> None:
        """Pick this frame's zoom and camera from the room the player is in."""
        width, height = self.screen.get_size()
        room = self.map.room_by_id(room_id)

        if room is None:
            target_scale = 1.0
            target = pygame.Vector2(focus_x - width / 2, focus_y - height / 2)
        else:
            rect = self._room_pixels(room)
            target_scale = min(
                ROOM_FILL * width / rect.width,
                ROOM_FILL * height / rect.height,
            )
            target_scale = max(MIN_SCALE, min(MAX_SCALE, target_scale))

            visible_w = width / target_scale
            visible_h = height / target_scale
            if rect.width <= visible_w and rect.height <= visible_h:
                target = pygame.Vector2(
                    rect.centerx - visible_w / 2, rect.centery - visible_h / 2
                )
            else:
                # Room larger than the screen at the minimum zoom: follow the
                # player but never show past the room's own walls.
                target = pygame.Vector2(
                    self._clamp(focus_x - visible_w / 2, rect.left, rect.right - visible_w),
                    self._clamp(focus_y - visible_h / 2, rect.top, rect.bottom - visible_h),
                )

        if self._settled:
            self.scale += (target_scale - self.scale) * EASE
            self.camera += (target - self.camera) * EASE
        else:
            self.scale, self.camera = target_scale, target
            self._settled = True

    def _room_pixels(self, room: dict[str, Any]) -> pygame.Rect:
        size = self.map.tile_size
        x, y, w, h = room["rect"]
        return pygame.Rect(x * size, y * size, w * size, h * size)

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return low if high < low else max(low, min(high, value))

    def to_screen(self, world_x: float, world_y: float) -> tuple[float, float]:
        return (
            (world_x - self.camera.x) * self.scale,
            (world_y - self.camera.y) * self.scale,
        )

    def to_world(self, screen_x: float, screen_y: float) -> tuple[float, float]:
        return (
            screen_x / self.scale + self.camera.x,
            screen_y / self.scale + self.camera.y,
        )

    def draw(
        self,
        room_id: str | None,
        me: dict[str, Any] | None,
        others: list[dict[str, Any]],
        status: list[str],
    ) -> None:
        self.screen.fill(BACKGROUND)
        self._blit_world(self.map.world_dim, self._visible_world_rect())

        room = self.map.room_by_id(room_id)
        if room is not None:
            self._blit_world(self.map.world, self._room_pixels(room))

        for other in others:
            self._draw_player(other["x"], other["y"], other["c"])
        if me is not None:
            self._draw_player(me["x"], me["y"], me["c"], mark=True)

        self._blit_world(self.map.foreground, self._visible_world_rect())

        for index, line in enumerate(status):
            self.screen.blit(self.font.render(line, True, TEXT), (12, 10 + index * 20))

    def _visible_world_rect(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        return pygame.Rect(
            int(self.camera.x),
            int(self.camera.y),
            int(width / self.scale) + 1,
            int(height / self.scale) + 1,
        )

    def _blit_world(self, source: pygame.Surface, world_rect: pygame.Rect) -> None:
        clipped = world_rect.clip(self._visible_world_rect()).clip(source.get_rect())
        if clipped.width <= 0 or clipped.height <= 0:
            return
        slice_ = source.subsurface(clipped)
        target = pygame.Rect(
            *self.to_screen(clipped.x, clipped.y),
            max(1, round(clipped.width * self.scale)),
            max(1, round(clipped.height * self.scale)),
        )
        self.screen.blit(pygame.transform.scale(slice_, target.size), target.topleft)

    def _draw_player(self, x: float, y: float, color: list[int], mark: bool = False) -> None:
        left, top = self.to_screen(x, y)
        rect = pygame.Rect(
            round(left),
            round(top),
            max(1, round(self.tuning["player_width"] * self.scale)),
            max(1, round(self.tuning["player_height"] * self.scale)),
        )
        self.screen.fill(color, rect)
        if mark:
            pygame.draw.rect(self.screen, OUTLINE, rect, width=1)
