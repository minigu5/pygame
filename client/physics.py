"""A copy of the server's step function, used only to predict my own body.

The server stays authoritative. This exists so my own input shows up on the
next frame instead of one round trip later; anything it gets wrong is pulled
back when the next snapshot arrives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playerinput import JUMP, LEFT, RIGHT

@dataclass
class Body:
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    on_ground: bool = False
    frozen: bool = False
    coyote_ms: float = 0.0
    jump_buffer_ms: float = 0.0
    jump_held: bool = False

    def copy(self) -> "Body":
        return Body(**vars(self))


class Physics:
    def __init__(self, game_map, tuning: dict[str, Any]) -> None:
        self.map = game_map
        self.tuning = tuning
        self.solid_by_index = [entry["solid"] for entry in game_map.palette]

    def is_solid(self, col: int, row: int) -> bool:
        if col < 0 or row < 0 or col >= self.map.width or row >= self.map.height:
            return True
        return self.solid_by_index[self.map.solid[row][col]]

    def overlaps(self, x: float, y: float) -> bool:
        size = self.map.tile_size
        left = int(x // size)
        right = int((x + self.tuning["player_width"] - 1) // size)
        top = int(y // size)
        bottom = int((y + self.tuning["player_height"] - 1) // size)
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if self.is_solid(col, row):
                    return True
        return False

    def step(self, body: Body, mask: int, dt_ms: float) -> None:
        if body.frozen:
            body.vx = body.vy = 0.0
            return

        tuning = self.tuning
        dt = dt_ms / 1000
        wants_jump = bool(mask & JUMP)

        if wants_jump and not body.jump_held:
            body.jump_buffer_ms = tuning["jump_buffer_ms"]
        else:
            body.jump_buffer_ms = max(0.0, body.jump_buffer_ms - dt_ms)

        if not wants_jump and body.jump_held and body.vy < 0:
            body.vy *= tuning["short_hop_factor"]
        body.jump_held = wants_jump

        direction = (1 if mask & RIGHT else 0) - (1 if mask & LEFT else 0)
        body.vx = direction * tuning["move_speed"]

        if body.jump_buffer_ms > 0 and body.coyote_ms > 0:
            body.vy = tuning["jump_speed"]
            body.jump_buffer_ms = 0.0
            body.coyote_ms = 0.0
            body.on_ground = False

        body.vy = min(body.vy + tuning["gravity"] * dt, tuning["max_fall_speed"])

        self._move_x(body, body.vx * dt)
        landed = self._move_y(body, body.vy * dt)

        body.on_ground = landed
        body.coyote_ms = tuning["coyote_ms"] if landed else max(0.0, body.coyote_ms - dt_ms)

    def _move_x(self, body: Body, delta: float) -> None:
        if delta == 0:
            return
        target = body.x + delta
        if not self.overlaps(target, body.y):
            body.x = target
            return
        step_px = 1 if delta > 0 else -1
        while not self.overlaps(body.x + step_px, body.y):
            body.x += step_px
        body.vx = 0.0

    def _move_y(self, body: Body, delta: float) -> bool:
        if delta == 0:
            return body.on_ground and not self.overlaps(body.x, body.y + 1)
        target = body.y + delta
        if not self.overlaps(body.x, target):
            body.y = target
            return False
        step_px = 1 if delta > 0 else -1
        while not self.overlaps(body.x, body.y + step_px):
            body.y += step_px
        landed = delta > 0
        body.vy = 0.0
        return landed
