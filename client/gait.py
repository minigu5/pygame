"""Which step of the walk cycle each body is on, and which way it faces."""

from __future__ import annotations

from body_shape import WALK_FRAMES

STRIDE_PX = 100.0   # world px per full cycle (two steps), so a run is about four steps a second
MIN_STEP_PX = 0.3   # slower than this per frame is standing still
MAX_RISE_PX = 2.0   # more than this per frame is a jump or a fall, not a step


class Gait:
    """Advances a walk phase per body from its motion frame to frame.

    A body that stands, jumps or falls has no frame (it is drawn at
    attention); one that walks steps through the cycle as far as it moves,
    and turns to face the way it goes.
    """

    def __init__(self) -> None:
        self._phase: dict[str, float] = {}
        self._last: dict[str, tuple[float, float]] = {}
        self._facing: dict[str, int] = {}

    def frame(
        self, key: str, x: float, y: float, walking: bool | None = None, direction: int = 0
    ) -> int | None:
        """The walk frame for a body now at (x, y), or None when it is not walking.

        `walking` and `direction` (+1 right, -1 left, 0 unknown) override what
        its motion suggests, for the body whose speed is known exactly.
        """
        last = self._last.get(key)
        self._last[key] = (x, y)
        dx, dy = (0.0, 0.0) if last is None else (x - last[0], y - last[1])
        if direction == 0 and abs(dx) >= MIN_STEP_PX:
            direction = 1 if dx > 0 else -1
        if direction != 0:
            self._facing[key] = direction
        if walking is None:
            walking = last is not None and abs(dx) >= MIN_STEP_PX and abs(dy) <= MAX_RISE_PX
        if not walking:
            self._phase[key] = 0.0
            return None
        phase = (self._phase.get(key, 0.0) + abs(dx) / STRIDE_PX) % 1.0
        self._phase[key] = phase
        return int(phase * WALK_FRAMES)

    def facing(self, key: str) -> int:
        """+1 when the body last moved right (the way the walk is drawn), -1 for left."""
        return self._facing.get(key, 1)

    def forget(self, key: str) -> None:
        self._phase.pop(key, None)
        self._last.pop(key, None)
        self._facing.pop(key, None)

    def clear(self) -> None:
        self._phase.clear()
        self._last.clear()
        self._facing.clear()
