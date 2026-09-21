"""Samples keys every frame and ships them in small batches."""

from __future__ import annotations

import pygame

LEFT = 1
RIGHT = 2
JUMP = 4


def sample() -> int:
    keys = pygame.key.get_pressed()
    mask = 0
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        mask |= LEFT
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        mask |= RIGHT
    if keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]:
        mask |= JUMP
    return mask


class InputBatcher:
    """Collects one mask per frame and releases them `batch_size` at a time.

    Sending every frame would multiply the billed request count; sending a
    single mask per packet would blur jump timing. Batching keeps both.
    """

    def __init__(self, batch_size: int) -> None:
        self.batch_size = batch_size
        self.sequence = 0
        self._frames: list[int] = []

    def push(self, mask: int) -> dict | None:
        self._frames.append(mask)
        if len(self._frames) < self.batch_size:
            return None
        self.sequence += 1
        message = {"t": "i", "n": self.sequence, "k": self._frames}
        self._frames = []
        return message
