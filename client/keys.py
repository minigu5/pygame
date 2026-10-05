"""Shortcuts that work whichever way the 한/영 key is set.

Two things get between a key and the game when a Korean input method is on.
While text input is active the IME takes the letter keys for composing, so M
never arrives at all: the game therefore keeps text input off except while a
text field is being typed in (see ui_widgets.TextField). And on some systems
the key that does arrive is named after the jamo printed on it (ㅡ) rather
than the letter (M): latin_key() reads those back as the letter.
"""

from __future__ import annotations

import pygame

# Dubeolsik, the standard Korean layout: each jamo and the letter that shares its key.
JAMO_KEYS = {
    "ㅂ": "q", "ㅈ": "w", "ㄷ": "e", "ㄱ": "r", "ㅅ": "t", "ㅛ": "y", "ㅕ": "u", "ㅑ": "i", "ㅐ": "o", "ㅔ": "p",
    "ㅁ": "a", "ㄴ": "s", "ㅇ": "d", "ㄹ": "f", "ㅎ": "g", "ㅗ": "h", "ㅓ": "j", "ㅏ": "k", "ㅣ": "l",
    "ㅋ": "z", "ㅌ": "x", "ㅊ": "c", "ㅍ": "v", "ㅠ": "b", "ㅜ": "n", "ㅡ": "m",
    # With Shift held.
    "ㅃ": "q", "ㅉ": "w", "ㄸ": "e", "ㄲ": "r", "ㅆ": "t", "ㅒ": "o", "ㅖ": "p",
}

_SCANCODE_A = pygame.KSCAN_A
_SCANCODE_Z = pygame.KSCAN_Z


def latin_key(event: pygame.event.Event) -> int:
    """The pygame key a KEYDOWN/KEYUP stands for, with jamo read as their letters."""
    key = event.key
    if 0 < key < 128:
        return key
    for text in (chr(key) if 0 < key < 0x110000 else "", getattr(event, "unicode", "")):
        letter = JAMO_KEYS.get(text)
        if letter is not None:
            return ord(letter)
    # No name we know: go by where the key sits on the keyboard.
    scancode = getattr(event, "scancode", 0)
    if _SCANCODE_A <= scancode <= _SCANCODE_Z:
        return pygame.K_a + scancode - _SCANCODE_A
    return key


def game_keys() -> None:
    """Keys are for playing: no IME composing, no auto-repeat. It acts on the
    window that has the keyboard, so it is called again whenever focus returns."""
    pygame.key.stop_text_input()
    pygame.key.set_repeat()
