"""Local prediction for my body and interpolation for everyone else's."""

from __future__ import annotations

import time
from typing import Any

from physics import Body, Physics

SNAP_THRESHOLD = 8.0   # px; below this a correction is not worth easing
EASE_PER_FRAME = 0.6   # leftover error after each frame, so ~3 frames to settle


class Predictor:
    """Replays my unacknowledged inputs on top of the server's last word."""

    def __init__(self, physics: Physics, tick_ms: float) -> None:
        self.physics = physics
        self.tick_ms = tick_ms
        self.body: Body | None = None
        self.history: list[tuple[int, int]] = []  # (frame number, key mask)
        self.offset_x = 0.0
        self.offset_y = 0.0

    def record(self, frame: int, mask: int) -> None:
        self.history.append((frame, mask))

    def advance(self, mask: int) -> None:
        if self.body is not None:
            self.physics.step(self.body, mask, self.tick_ms)

    def reconcile(self, state: dict[str, Any], acked_frame: int) -> None:
        self.history = [entry for entry in self.history if entry[0] > acked_frame]

        if self.body is None:
            self.body = Body(x=float(state["x"]), y=float(state["y"]))
        before_x, before_y = self.body.x, self.body.y

        self.body.x = float(state["x"])
        self.body.y = float(state["y"])
        self.body.vy = float(state["vy"])
        self.body.on_ground = bool(state["g"])
        self.body.frozen = bool(state["fz"])

        for _, mask in self.history:
            self.physics.step(self.body, mask, self.tick_ms)

        # Carry the jump as a visual offset that decays, so a correction reads
        # as a quick settle rather than a teleport.
        self.offset_x += before_x - self.body.x
        self.offset_y += before_y - self.body.y
        if abs(self.offset_x) < SNAP_THRESHOLD / 8:
            self.offset_x = 0.0
        if abs(self.offset_y) < SNAP_THRESHOLD / 8:
            self.offset_y = 0.0

    def render_position(self) -> tuple[float, float]:
        if self.body is None:
            return 0.0, 0.0
        x = self.body.x + self.offset_x
        y = self.body.y + self.offset_y
        self.offset_x *= EASE_PER_FRAME
        self.offset_y *= EASE_PER_FRAME
        return x, y


class Interpolator:
    """Draws other players slightly in the past so motion stays smooth."""

    def __init__(self, delay_ms: float) -> None:
        self.delay = delay_ms / 1000
        self.samples: list[tuple[float, dict[str, dict[str, Any]]]] = []

    def push(self, players: list[dict[str, Any]]) -> None:
        frame = {player["i"]: player for player in players}
        self.samples.append((time.monotonic(), frame))
        if len(self.samples) > 8:
            self.samples.pop(0)

    def drop(self, player_id: str) -> None:
        for _, frame in self.samples:
            frame.pop(player_id, None)

    def at_now(self) -> list[dict[str, Any]]:
        if not self.samples:
            return []

        target = time.monotonic() - self.delay
        older = newer = None
        for index in range(len(self.samples) - 1):
            if self.samples[index][0] <= target <= self.samples[index + 1][0]:
                older, newer = self.samples[index], self.samples[index + 1]
                break

        if older is None or newer is None:
            return list(self.samples[-1][1].values())

        span = newer[0] - older[0]
        ratio = 0.0 if span <= 0 else (target - older[0]) / span

        blended = []
        for player_id, start in older[1].items():
            end = newer[1].get(player_id)
            if end is None:
                continue
            blended.append(
                {
                    "i": player_id,
                    "x": start["x"] + (end["x"] - start["x"]) * ratio,
                    "y": start["y"] + (end["y"] - start["y"]) * ratio,
                    "fz": end["fz"],
                    "c": end["c"],
                }
            )
        return blended
