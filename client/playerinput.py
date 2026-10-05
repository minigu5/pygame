"""Samples keys every frame and ships them in small batches."""

from __future__ import annotations

import pygame

LEFT = 1
RIGHT = 2
JUMP = 4
UP = 8
DOWN = 16


def sample() -> int:
    """This frame's key mask. Space is the freeze toggle, so it is not here;
    W jumps, and the arrows climb a ladder until a stair key is chosen."""
    keys = pygame.key.get_pressed()
    mask = 0
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        mask |= LEFT
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        mask |= RIGHT
    if keys[pygame.K_w]:
        mask |= JUMP
    if keys[pygame.K_UP]:
        mask |= UP
    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        mask |= DOWN
    return mask


def sample_frozen() -> int:
    """This frame's key mask while frozen: WASD slide the pinned body, W
    upwards rather than jumping. The arrows are left out, they pick the pose."""
    keys = pygame.key.get_pressed()
    mask = 0
    if keys[pygame.K_a]:
        mask |= LEFT
    if keys[pygame.K_d]:
        mask |= RIGHT
    if keys[pygame.K_w]:
        mask |= UP
    if keys[pygame.K_s]:
        mask |= DOWN
    return mask


class FramePacer:
    """How many input frames to play for each frame drawn.

    The server steps the body once for every input frame, a sixtieth of a
    second each, so the frames have to come at that rate whatever the screen
    does. Near it, one a frame is right and a little drift is the server's to
    absorb. Far from it (a slow browser, a 144Hz display) they are counted
    out by the clock instead, or the body would crawl or sprint.
    """

    LOCKED = (0.85, 1.15)   # input frames per drawn frame taken as "the same rate"
    MOST = 6                # input frames in one drawn frame; a longer stall is not made up

    def __init__(self, frame_seconds: float) -> None:
        self.frame_seconds = frame_seconds
        self.last: float | None = None
        self.rate = 1.0     # input frames per drawn frame, smoothed
        self.owed = 0.0

    def rest(self) -> None:
        """Nothing is being played: the time that passes meanwhile is not owed."""
        self.last = None
        self.owed = 0.0

    def frames(self, now: float) -> int:
        if self.last is None:
            self.last = now
            return 1
        elapsed = min((now - self.last) / self.frame_seconds, self.MOST)
        self.last = now
        self.rate += (elapsed - self.rate) * 0.1
        if self.LOCKED[0] <= self.rate <= self.LOCKED[1]:
            self.owed = 0.0
            return 1
        self.owed += elapsed
        count = int(self.owed)
        self.owed -= count
        return count


class InputBatcher:
    """Collects one mask per frame and releases them `batch_size` at a time.

    Sending every frame would multiply the billed request count; sending a
    single mask per packet would blur jump timing. Batching keeps both.
    """

    def __init__(self, batch_size: int) -> None:
        self.batch_size = batch_size
        self.frame = 0
        self._first_frame = 1
        self._frames: list[int] = []

    def push(self, mask: int) -> tuple[int, dict | None]:
        """Record this frame's mask; returns its frame number and any packet."""
        self.frame += 1
        if not self._frames:
            self._first_frame = self.frame
        self._frames.append(mask)
        if len(self._frames) < self.batch_size:
            return self.frame, None
        message = {"t": "i", "n": self._first_frame, "k": self._frames}
        self._frames = []
        return self.frame, message
