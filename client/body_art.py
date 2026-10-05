"""Other players' paintings: packing mine to send, and drawing theirs.

A hunter has to see the body the chameleon actually painted, so the whole
canvas goes over the wire: its RGB bytes, deflated, in base64 so it fits in a
JSON message. A freshly filled canvas packs to a few dozen bytes and a busy
one to a few kilobytes, and it is only sent when a stroke ends.
"""

from __future__ import annotations

import base64
import binascii
import zlib

import pygame

import body_shape

SPRITE_CACHE = 96


def pack(canvas: pygame.Surface) -> str:
    return base64.b64encode(zlib.compress(pygame.image.tobytes(canvas, "RGB"), 6)).decode("ascii")


def unpack(packed: str) -> pygame.Surface | None:
    """The canvas a peer sent, or None if it is not one: it came from outside."""
    width, height = body_shape.canvas_size()
    size = width * height * 3
    try:
        inflater = zlib.decompressobj()
        # Never inflate more than a canvas: a few bytes can claim to be gigabytes.
        raw = inflater.decompress(base64.b64decode(packed, validate=True), size)
    except (binascii.Error, ValueError, zlib.error):
        return None
    if len(raw) != size or inflater.unconsumed_tail:
        return None
    canvas = pygame.Surface((width, height), 0, 32)
    canvas.blit(pygame.image.frombytes(raw, (width, height), "RGB"), (0, 0))
    return canvas


class ArtBook:
    """The paintings received so far, by player id, cut to whatever pose is asked for."""

    def __init__(self) -> None:
        self._canvases: dict[str, pygame.Surface] = {}
        self._sprites: dict[tuple[str, str, int], pygame.Surface] = {}

    def put(self, player_id: str, packed: str) -> None:
        canvas = unpack(packed)
        if canvas is None:
            return
        self._canvases[player_id] = canvas
        self._drop_sprites(player_id)

    def forget(self, player_id: str) -> None:
        self._canvases.pop(player_id, None)
        self._drop_sprites(player_id)

    def clear(self) -> None:
        self._canvases.clear()
        self._sprites.clear()

    def sprite(self, player_id: str, pose: str, frame: int = 0) -> pygame.Surface | None:
        """The player's painted body in this pose, or None if no painting has come."""
        canvas = self._canvases.get(player_id)
        if canvas is None:
            return None
        frame = frame % body_shape.WALK_FRAMES if pose == "walk" else 0
        key = (player_id, pose, frame)
        if key not in self._sprites:
            if len(self._sprites) >= SPRITE_CACHE:
                self._sprites.clear()
            self._sprites[key] = body_shape.sprite(canvas, pose, frame)
        return self._sprites[key]

    def _drop_sprites(self, player_id: str) -> None:
        for key in [key for key in self._sprites if key[0] == player_id]:
            del self._sprites[key]
