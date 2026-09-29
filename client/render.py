"""Room-framed camera: the current room fills the middle of the screen and
everything beyond it is drained to grey."""

from __future__ import annotations

from typing import Any
import math

import pygame

import body_shape
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
        self.zoom = 1.0         # extra zoom on top of the room's own, for painting
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
                # For stairwells, we want to track vertically but center horizontally in the room
                if room.get("stairs", False):
                    # Center horizontally in room, track vertically
                    target_x = rect.centerx - visible_w / 2
                    target_y = self._clamp(focus_y - visible_h / 2, rect.top, rect.bottom - visible_h)
                    target = pygame.Vector2(target_x, target_y)
                else:
                    target = pygame.Vector2(
                        self._clamp(focus_x - visible_w / 2, rect.left, rect.right - visible_w),
                        self._clamp(focus_y - visible_h / 2, rect.top, rect.bottom - visible_h),
                    )

        if self.zoom > 1.0:
            # Zoomed in to paint: keep the player in the middle, walls or not.
            target_scale *= self.zoom
            target = pygame.Vector2(
                focus_x - width / target_scale / 2, focus_y - height / target_scale / 2
            )

        # Frame-independent exponential decay interpolation
        # position_speed = 8.0, zoom_speed = 6.0 (units: per second)
        dt = 1.0 / 60.0  # Assuming 60 FPS, but we'll make this more precise if needed
        if self._settled:
            # Position interpolation: 1 - e^(-position_speed * dt)
            pos_factor = 1.0 - math.exp(-8.0 * dt)
            self.camera += (target - self.camera) * pos_factor
            
            # Zoom interpolation: 1 - e^(-zoom_speed * dt)
            zoom_factor = 1.0 - math.exp(-6.0 * dt)
            self.scale += (target_scale - self.scale) * zoom_factor
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
            # Only a colour comes over the wire, and no pose: a flat standing
            # figure, walking side-on when it moves.
            frame = other.get("frame")
            if frame is None:
                sprite = body_shape.solid_sprite(other["c"], "stand")
            else:
                sprite = body_shape.solid_sprite(other["c"], "walk", frame)
                if other.get("facing", 1) < 0:
                    sprite = pygame.transform.flip(sprite, True, False)
            self._draw_body(sprite, "stand", other["x"], other["y"])
        if me is not None:
            self._draw_body(me["sprite"], me["pose"], me["x"], me["y"], mark=True)

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

    def body_rect(self, pose: str, x: float, y: float) -> pygame.Rect:
        """Where a body in `pose` whose hitbox is at (x, y) is drawn on screen this frame."""
        # The collision box covers the whole pixel rows floor(y) .. floor(y)+31,
        # so a body resting at y=112.9 stands on row 144: drawn from 112.9 its
        # feet would hang a pixel into the floor.
        world = body_shape.pose_rect(pose, x, math.floor(y), self.tuning["player_width"], self.tuning["player_height"])
        left, top = self.to_screen(world.x, world.y)
        _, bottom = self.to_screen(world.x, world.bottom)
        # Sized from the rounded bottom edge, not the rounded height, so the
        # feet land on the same screen row as the floor tile's top edge.
        height = max(1, round(bottom) - round(top))
        return pygame.Rect(
            round(left),
            round(top),
            max(1, round(world.width * self.scale)),
            height,
        )

    def _draw_body(self, sprite: pygame.Surface, pose: str, x: float, y: float, mark: bool = False) -> None:
        rect = self.body_rect(pose, x, y)
        if not rect.colliderect(self.screen.get_rect()):
            # Zoomed in to paint, the rest of the room is off screen: no point
            # scaling a body nobody sees.
            return
        # Smooth scaling both ways: the painting is finer than the screen
        # unzoomed, and reads as brushwork rather than blocks when zoomed in.
        self.screen.blit(pygame.transform.smoothscale(sprite, rect.size), rect.topleft)
        if mark:
            # A small arrow over my own head, the same size at any zoom, so it
            # never sits on the silhouette's edge while I paint.
            cx, top = rect.centerx, rect.top
            points = [(cx - 5, top - 12), (cx + 5, top - 12), (cx, top - 5)]
            pygame.draw.polygon(self.screen, TEXT, points)
            pygame.draw.polygon(self.screen, OUTLINE, points, width=1)
