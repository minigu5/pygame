"""Local prediction for my body and interpolation for everyone else's."""

from __future__ import annotations

import time
from typing import Any

from physics import Body, Physics

SNAP_THRESHOLD = 8.0   # px; below this a correction is not worth easing
EASE_PER_FRAME = 0.6   # leftover error after each frame, so ~3 frames to settle
# A snapshot rounds x and y to whole pixels, so half a pixel of disagreement is
# no disagreement at all. Anything under this is left alone rather than
# corrected, which would only rattle the body with every snapshot.
AGREE_PX = 1.0


class Predictor:
    """Replays my unacknowledged inputs on top of the server's last word.

    Every predicted frame is kept with the body as it was after that frame.
    When a snapshot acknowledges a frame, it is compared with what I predicted
    for that same frame: if they agree, nothing changes; if they do not, the
    body is rebuilt from the server's word plus the rest of my own state as it
    was at that frame (jump held, coyote time, speed) and the frames after it
    are replayed. Replaying from the present state instead would, for example,
    drop a jump pressed in the meantime because the key already reads as held.
    """

    def __init__(self, physics: Physics, tick_ms: float) -> None:
        self.physics = physics
        self.tick_ms = tick_ms
        self.body: Body | None = None
        self.history: list[tuple[int, int, Body]] = []  # (frame number, key mask, body after it)
        self.offset_x = 0.0
        self.offset_y = 0.0

    def step(self, frame: int, mask: int) -> None:
        """Advance my body by one frame of input and remember the result."""
        if self.body is None:
            return
        self.physics.step(self.body, mask, self.tick_ms)
        self.history.append((frame, mask, self.body.copy()))

    def reset(self) -> None:
        self.body = None
        self.history.clear()
        self.offset_x = self.offset_y = 0.0

    def reconcile(self, state: dict[str, Any], acked_frame: int) -> None:
        predicted = next((entry[2] for entry in self.history if entry[0] == acked_frame), None)
        self.history = [entry for entry in self.history if entry[0] > acked_frame]

        if self.body is None:
            self.body = self._from_server(Body(x=float(state["x"]), y=float(state["y"])), state)
            self._replay()
            return

        if predicted is not None and self._agrees(predicted, state):
            return

        before_x, before_y = self.body.x, self.body.y
        # What I knew at that frame, corrected by what the server knows.
        base = predicted.copy() if predicted is not None else self.body.copy()
        self.body = self._from_server(base, state)
        self._replay()

        # Carry the jump as a visual offset that decays, so a correction reads
        # as a quick settle rather than a teleport.
        self.offset_x += before_x - self.body.x
        self.offset_y += before_y - self.body.y
        if abs(self.offset_x) < SNAP_THRESHOLD / 8:
            self.offset_x = 0.0
        if abs(self.offset_y) < SNAP_THRESHOLD / 8:
            self.offset_y = 0.0

    @staticmethod
    def _agrees(predicted: Body, state: dict[str, Any]) -> bool:
        return (
            abs(predicted.x - float(state["x"])) <= AGREE_PX
            and abs(predicted.y - float(state["y"])) <= AGREE_PX
            and predicted.on_ground == bool(state["g"])
            and predicted.frozen == bool(state["fz"])
        )

    @staticmethod
    def _from_server(body: Body, state: dict[str, Any]) -> Body:
        body.x = float(state["x"])
        body.y = float(state["y"])
        body.vy = float(state["vy"])
        body.on_ground = bool(state["g"])
        body.frozen = bool(state["fz"])
        return body

    def _replay(self) -> None:
        assert self.body is not None
        replayed = []
        for frame, mask, _ in self.history:
            self.physics.step(self.body, mask, self.tick_ms)
            replayed.append((frame, mask, self.body.copy()))
        self.history = replayed

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
