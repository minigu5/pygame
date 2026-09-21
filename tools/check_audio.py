"""Check the generated tones exist, carry signal, and fail quietly.

The game ships no audio files; every sound is synthesised at startup. That
keeps the repository free of binaries but means a silent bug is invisible, so
this renders each voice and looks at the samples.

Usage: python tools/check_audio.py
"""

from __future__ import annotations

import os
import sys
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
        samples = sound.get_raw()
        peak = max(abs(int.from_bytes(samples[i : i + 2], "little", signed=True))
                   for i in range(0, len(samples), 2))
        if peak < 1000:
            silent.append(name)
        if sound.get_length() > 0.6:
            too_long.append(f"{name} {sound.get_length():.2f}s")

    check("no voice is silent", not silent, ", ".join(silent))
    check("no voice outstays its moment", not too_long, ", ".join(too_long))

    audio.toggle()
    audio.play("caught")
    check("muting stops playback without error", audio.enabled is False)

    quiet = Audio.__new__(Audio)
    quiet.enabled = False
    quiet.sounds = {}
    quiet.play("caught")
    check("a machine with no audio device still plays the game", True)

    pygame.quit()
    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
