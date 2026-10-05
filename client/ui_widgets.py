"""Buttons, a one-line text field and a small dialog, for the screens around the game."""

from __future__ import annotations

import pygame

from fonts import drawable, ui_font

PANEL_BG = (28, 30, 38)
PANEL_EDGE = (72, 76, 90)
TEXT = (232, 234, 240)
LABEL = (198, 202, 212)
DIM = (140, 145, 158)
BUTTON = (46, 50, 62)
BUTTON_HOVER = (58, 63, 78)
BUTTON_PRIMARY = (72, 108, 184)
BUTTON_PRIMARY_HOVER = (92, 132, 210)
BUTTON_OFF = (36, 38, 46)
LABEL_OFF = (96, 100, 112)
FIELD_BG = (18, 20, 26)
FIELD_EDGE_FOCUS = (92, 132, 210)
COMPOSING = (150, 190, 255)
VEIL = (10, 11, 15, 170)

KEY_REPEAT_MS = (400, 35)   # for a held Backspace while typing


class Button:
    def __init__(self, label: str, primary: bool = False, sign: int = 0) -> None:
        self.label = label
        self.primary = primary
        # -1 or +1 draws a minus or plus in strokes instead of a label: the
        # font's own minus sign is one of the glyphs it does not have.
        self.sign = sign
        self.enabled = True
        self.rect = pygame.Rect(0, 0, 0, 0)

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.enabled and self.rect.collidepoint(pos)

    def draw(self, screen: pygame.Surface, rect: pygame.Rect, size: int = 16) -> None:
        self.rect = rect
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if not self.enabled:
            fill, ink = BUTTON_OFF, LABEL_OFF
        elif self.primary:
            fill, ink = (BUTTON_PRIMARY_HOVER if hover else BUTTON_PRIMARY), TEXT
        else:
            fill, ink = (BUTTON_HOVER if hover else BUTTON), LABEL
        pygame.draw.rect(screen, fill, rect, border_radius=6)
        if self.sign:
            arm = rect.width // 5
            cx, cy = rect.center
            pygame.draw.line(screen, ink, (cx - arm, cy), (cx + arm, cy), width=2)
            if self.sign > 0:
                pygame.draw.line(screen, ink, (cx, cy - arm), (cx, cy + arm), width=2)
            return
        text = ui_font(size).render(self.label, True, ink)
        screen.blit(text, text.get_rect(center=rect.center))


class TextField:
    """One line of text. Typing goes through the system's input method only
    while the field has the focus: that is what lets Hangul be composed here
    without the IME swallowing the game's letter keys everywhere else."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars
        self.text = ""
        self.composing = ""     # the syllable the IME is still putting together
        self.focused = False
        self.rect = pygame.Rect(0, 0, 0, 0)

    def focus(self, text: str) -> None:
        self.text = text
        self.composing = ""
        self.focused = True
        pygame.key.start_text_input()
        pygame.key.set_text_input_rect(self.rect)
        pygame.key.set_repeat(*KEY_REPEAT_MS)

    def blur(self) -> None:
        if not self.focused:
            return
        self.focused = False
        self.composing = ""
        pygame.key.stop_text_input()
        pygame.key.set_repeat()

    def on_event(self, event: pygame.event.Event) -> str | None:
        """Takes the event if the field is being typed in. Returns "commit" on
        Enter, "cancel" on Escape, "" for anything else it used, None if the
        event was not for the field."""
        if not self.focused:
            return None
        if event.type == pygame.TEXTEDITING:
            self.composing = event.text
            return ""
        if event.type == pygame.TEXTINPUT:
            self.composing = ""
            room = self.max_chars - len(self.text)
            # Only what the font can show: a name must not read as boxes to anyone.
            self.text += "".join(ch for ch in event.text if drawable(ch))[: max(0, room)]
            return ""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "commit"
            if event.key == pygame.K_ESCAPE:
                return "cancel"
            if event.key == pygame.K_BACKSPACE and not self.composing:
                self.text = self.text[:-1]
            return ""
        if event.type == pygame.KEYUP:
            return ""
        return None

    def draw(self, screen: pygame.Surface, rect: pygame.Rect, size: int = 16) -> None:
        self.rect = rect
        font = ui_font(size)
        pygame.draw.rect(screen, FIELD_BG, rect, border_radius=4)
        pygame.draw.rect(screen, FIELD_EDGE_FOCUS if self.focused else PANEL_EDGE, rect, width=1, border_radius=4)
        x = rect.x + 8
        clip = screen.get_clip()
        screen.set_clip(rect.inflate(-8, 0))
        for text, ink in ((self.text, TEXT), (self.composing if self.focused else "", COMPOSING)):
            if text:
                label = font.render(text, True, ink)
                screen.blit(label, label.get_rect(midleft=(x, rect.centery)))
                x += label.get_width()
        if self.focused and pygame.time.get_ticks() % 1000 < 500:
            pygame.draw.line(screen, TEXT, (x + 1, rect.y + 6), (x + 1, rect.bottom - 7))
        screen.set_clip(clip)


class Dialog:
    """A box in the middle of the screen with a heading, a line of detail and a
    row of choices; everything behind it is dimmed."""

    def __init__(self, title: str, detail: str, choices: list[tuple[str, str]]) -> None:
        self.title = title
        self.detail = detail
        self.buttons = [(key, Button(label, primary=index == 0)) for index, (key, label) in enumerate(choices)]

    def choice_at(self, pos: tuple[int, int]) -> str | None:
        return next((key for key, button in self.buttons if button.hit(pos)), None)

    def draw(self, screen: pygame.Surface) -> None:
        veil = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        veil.fill(VEIL)
        screen.blit(veil, (0, 0))

        detail = ui_font(15).render(self.detail, True, DIM) if self.detail else None
        button_w, button_h, gap = 150, 40, 12
        buttons_w = len(self.buttons) * button_w + (len(self.buttons) - 1) * gap
        width = max(buttons_w, detail.get_width() if detail else 0) + 56
        box = pygame.Rect(0, 0, width, 176 if detail else 148)
        box.center = screen.get_rect().center
        pygame.draw.rect(screen, PANEL_BG, box, border_radius=10)
        pygame.draw.rect(screen, PANEL_EDGE, box, width=1, border_radius=10)

        title = ui_font(22).render(self.title, True, TEXT)
        screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 24)))
        if detail:
            screen.blit(detail, detail.get_rect(midtop=(box.centerx, box.y + 62)))

        x = box.centerx - buttons_w // 2
        for _, button in self.buttons:
            button.draw(screen, pygame.Rect(x, box.bottom - button_h - 24, button_w, button_h))
            x += button_w + gap
