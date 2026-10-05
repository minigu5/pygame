"""Short tones generated at startup, so the game ships no audio files.

The voices are plain sines with an envelope. They are not music; they are the
few moments where the player needs to be told something happened without
looking away from the wall they are painting. The one sound that is not a
tone is the brush: filtered noise that loops for as long as paint goes down.
"""

from __future__ import annotations

import array
import io
import math
import random
import time
import wave

import pygame

RATE = 22050
VOLUME = 0.35

# name -> (frequency steps in Hz, seconds per step)
VOICES: dict[str, tuple[tuple[float, ...], float]] = {
    "hide": ((523.25, 659.25), 0.12),      # round begins
    "seek": ((659.25, 523.25, 440.00), 0.11),
    "caught": ((880.00, 587.33, 392.00), 0.13),
    "miss": ((196.00, 164.81), 0.10),
    "freeze": ((440.00,), 0.06),
    "pick": ((1046.50,), 0.05),
    "result": ((392.00, 523.25, 659.25), 0.14),
}

BRUSH_SECONDS = 0.6     # one loop of the brush noise
BRUSH_VOLUME = 0.5      # peak; noise sits well under a sine of the same peak
BRUSH_HOLD = 0.12       # seconds the brush keeps sounding after the last paint
BRUSH_FADE_MS = 140


def _tone(steps: tuple[float, ...], step_seconds: float) -> pygame.mixer.Sound:
    samples = array.array("h")
    for frequency in steps:
        length = int(RATE * step_seconds)
        for index in range(length):
            # Fade each step in and out so the steps do not click into each other.
            progress = index / length
            envelope = min(1.0, progress * 12, (1.0 - progress) * 6)
            value = math.sin(2 * math.pi * frequency * index / RATE)
            samples.append(int(value * envelope * VOLUME * 32767))

    return _sound(samples)


def _brush() -> pygame.mixer.Sound:
    """Bristles dragged through wet paint: noise with the hiss and the rumble
    taken off, swelling unevenly, and cut so the end runs into the start."""
    length = int(RATE * BRUSH_SECONDS)
    overlap = length // 6
    noise = random.Random(7)    # the same brush on every machine
    raw = []
    smooth = rumble = 0.0
    for index in range(length + overlap):
        white = noise.uniform(-1.0, 1.0)
        smooth += 0.55 * (white - smooth)       # low-pass near 3kHz: no hiss
        rumble += 0.10 * (white - rumble)       # what lies under about 400Hz
        # Two swells that never line up within a loop, like an unsteady hand.
        # Both fit the loop a whole number of times so the seam stays silent.
        turn = 2 * math.pi * index / length
        swell = 0.72 + 0.18 * math.sin(4 * turn) + 0.10 * math.sin(7 * turn + 1.3)
        raw.append((smooth - rumble) * swell)
    # Fade the tail into the head so the loop has no click.
    for index in range(overlap):
        blend = index / overlap
        raw[index] = raw[index] * blend + raw[length + index] * (1.0 - blend)
    del raw[length:]

    peak = max(abs(value) for value in raw)
    samples = array.array("h", (int(value / peak * BRUSH_VOLUME * 32767) for value in raw))
    return _sound(samples)


def _sound(samples: array.array) -> pygame.mixer.Sound:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(samples.tobytes())
    buffer.seek(0)
    return pygame.mixer.Sound(file=buffer)


class Audio:
    def __init__(self) -> None:
        self.enabled = True
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.brush: pygame.mixer.Sound | None = None
        self._brush_channel: pygame.mixer.Channel | None = None
        self._brushing = False
        self._brush_until = 0.0
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=512)
        except pygame.error:
            # A machine with no output device should still play the game.
            self.enabled = False
            return
        self.sounds = {name: _tone(*voice) for name, voice in VOICES.items()}
        self.brush = _brush()
        # A channel of its own, so a tone never cuts the brush off or the other way round.
        pygame.mixer.set_reserved(1)
        self._brush_channel = pygame.mixer.Channel(0)

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def paint(self, stamped: bool) -> None:
        """Call every frame with whether paint went down in it: the brush
        sounds while it does and fades out shortly after it stops."""
        if self.brush is None or self._brush_channel is None:
            return
        now = time.monotonic()
        if stamped and self.enabled:
            self._brush_until = now + BRUSH_HOLD
            if not self._brushing:
                self._brush_channel.play(self.brush, loops=-1, fade_ms=30)
                self._brushing = True
        elif self._brushing and (now >= self._brush_until or not self.enabled):
            self._brush_channel.fadeout(BRUSH_FADE_MS)
            self._brushing = False

    def toggle(self) -> None:
        self.enabled = not self.enabled
