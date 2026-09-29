"""Short tones generated at startup, so the game ships no audio files.

Everything here is a plain sine with an envelope. It is not music; it is the
few moments where the player needs to be told something happened without
looking away from the wall they are painting.
"""

from __future__ import annotations

import array
import io
import math
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
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=512)
        except pygame.error:
            # A machine with no output device should still play the game.
            self.enabled = False
            return
        self.sounds = {name: _tone(*voice) for name, voice in VOICES.items()}

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            sound.play()

    def toggle(self) -> None:
        self.enabled = not self.enabled
