"""Check the generated tones exist, carry signal, and fail quietly.

The game ships no audio files; every sound is synthesised at startup. That
keeps the repository free of binaries but means a silent bug is invisible, so
this renders each voice and looks at the samples.

Usage: python tools/check_audio.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import pygame  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def sample_at(samples: bytes, index: int) -> int:
    return int.from_bytes(samples[index * 2 : index * 2 + 2], "little", signed=True)


def peak_of(sound: pygame.mixer.Sound) -> int:
    samples = sound.get_raw()
    return max(abs(sample_at(samples, index)) for index in range(len(samples) // 2))


def main() -> int:
    pygame.init()

    from audio import VOICES, Audio  # noqa: E402

    audio = Audio()
    check("the mixer came up", audio.enabled)
    check(
        "every voice was generated",
        set(audio.sounds) == set(VOICES),
        f"{len(audio.sounds)} of {len(VOICES)}",
    )

    silent = []
    too_long = []
    for name, sound in audio.sounds.items():
        if peak_of(sound) < 1000:
            silent.append(name)
        if sound.get_length() > 0.6:
            too_long.append(f"{name} {sound.get_length():.2f}s")

    check("no voice is silent", not silent, ", ".join(silent))
    check("no voice outstays its moment", not too_long, ", ".join(too_long))

    # The brush is noise, not a voice: it loops while paint goes down.
    check("the brush sound was generated", audio.brush is not None and peak_of(audio.brush) >= 1000)
    samples = audio.brush.get_raw()
    seam = abs(sample_at(samples, 0) - sample_at(samples, len(samples) // 2 - 1))
    check("the brush loop closes without a click", seam < 4000, f"step of {seam} across the seam")
    channel = pygame.mixer.Channel(0)
    audio.paint(False)
    check("the brush is quiet until paint goes down", not channel.get_busy())
    audio.paint(True)
    check("painting sounds the brush", channel.get_busy() and channel.get_sound() is audio.brush)
    audio.play("pick")
    check("a tone does not take the brush's channel", channel.get_sound() is audio.brush)
    audio.paint(False)
    check("the brush carries over a short gap in the stroke", audio._brushing)
    time.sleep(0.2)
    audio.paint(False)
    check("the brush stops when the painting does", not audio._brushing)

    audio.paint(True)
    audio.toggle()
    audio.play("caught")
    audio.paint(True)
    check("muting stops playback without error", audio.enabled is False and not audio._brushing)

    quiet = Audio.__new__(Audio)
    quiet.enabled = False
    quiet.sounds = {}
    quiet.brush = quiet._brush_channel = None
    quiet.play("caught")
    quiet.paint(True)
    check("a machine with no audio device still plays the game", True)

    pygame.quit()
    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
