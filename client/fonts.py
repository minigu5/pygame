"""One typeface for every label, so Hangul never comes out as empty boxes.

A font that lacks a glyph draws a box in its place, and the monospace faces
(Menlo, Courier New) have no Hangul at all: anything Korean that reached them,
a room name or the system's own error text, was unreadable. Every label goes
through here instead.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pygame

# macOS, Windows, then the usual Linux packages (fonts-noto-cjk, fonts-nanum).
KOREAN_FONTS = "applesdgothicneo,applegothic,malgungothic,notosanskr,notosanscjkkr,nanumgothic,nanumbarungothic,gulim,arialunicode"
# Noto Sans KR without its Hanja (SIL Open Font License): for where there are
# no system fonts to ask, which is every browser, and any machine with none of the above.
BUNDLED = Path(__file__).resolve().parent / "assets" / "fonts" / "NotoSansKR-Regular.ttf"


@lru_cache(maxsize=None)
def _system_font() -> str | None:
    return pygame.font.match_font(KOREAN_FONTS)


def has_korean() -> bool:
    """False on a machine with none of the fonts: labels must then stay ASCII."""
    return _system_font() is not None or BUNDLED.is_file()


@lru_cache(maxsize=None)
def ui_font(size: int) -> pygame.font.Font:
    if _system_font() is None and BUNDLED.is_file():
        return pygame.font.Font(str(BUNDLED), size)
    return pygame.font.SysFont(KOREAN_FONTS, size)


def is_box(font: pygame.font.Font, char: str) -> bool:
    """True when the font draws `char` as its missing-glyph box. Its metrics
    cannot say: a font reports the box's own for a character it lacks."""
    ink = (255, 255, 255)
    box = font.render("￿", True, ink)      # a noncharacter: no font has it
    drawn = font.render(char, True, ink)
    return drawn.get_size() == box.get_size() and pygame.image.tobytes(drawn, "RGBA") == pygame.image.tobytes(box, "RGBA")


@lru_cache(maxsize=4096)
def drawable(char: str) -> bool:
    """Whether the interface font can show this character at all."""
    return char.isprintable() and (char == " " or not is_box(ui_font(16), char))


def readable(text: str) -> str:
    """Text that came from outside (a room name someone else typed) with
    anything the font cannot show replaced, so it never reads as boxes."""
    return "".join(char if drawable(char) else "?" for char in text)
