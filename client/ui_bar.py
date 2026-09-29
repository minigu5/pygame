"""A strip of labelled buttons with one selected, stacked above another panel."""

from __future__ import annotations

import pygame

BAR_HEIGHT = 36
BAR_GAP = 8
PAD = 6
BUTTON_GAP = 6

PANEL_BG = (28, 30, 38)
PANEL_EDGE = (72, 76, 90)
LABEL = (198, 202, 212)
BUTTON = (46, 50, 62)
BUTTON_ACTIVE = (92, 132, 210)


class ButtonBar:
    def __init__(self, font: pygame.font.Font, labels: list[str], keys: tuple[int, ...] = ()) -> None:
        self.font = font
        self.labels = labels
        self.keys = keys
        self.selected = 0
        self._buttons: list[pygame.Rect] = []

    def select_key(self, key: int) -> bool:
        if key in self.keys:
            self.selected = self.keys.index(key)
            return True
        return False

    def on_mouse_down(self, pos: tuple[int, int]) -> bool:
        """Returns True when the click picked a button."""
        for index, button in enumerate(self._buttons):
            if button.collidepoint(pos):
                self.selected = index
                return True
        return False

    def contains(self, pos: tuple[int, int]) -> bool:
        return any(button.collidepoint(pos) for button in self._buttons)

    def draw_above(self, screen: pygame.Surface, below: pygame.Rect) -> pygame.Rect:
        """Draws the bar just above `below`, same width, and returns its rect."""
        rect = pygame.Rect(below.x, below.y - BAR_GAP - BAR_HEIGHT, below.width, BAR_HEIGHT)
        pygame.draw.rect(screen, PANEL_BG, rect, border_radius=8)
        pygame.draw.rect(screen, PANEL_EDGE, rect, width=1, border_radius=8)

        count = len(self.labels)
        button_w = (rect.width - PAD * 2 - BUTTON_GAP * (count - 1)) // count
        self._buttons = [
            pygame.Rect(rect.x + PAD + index * (button_w + BUTTON_GAP), rect.y + PAD, button_w, BAR_HEIGHT - PAD * 2)
            for index in range(count)
        ]
        for index, (label, button) in enumerate(zip(self.labels, self._buttons)):
            pygame.draw.rect(screen, BUTTON_ACTIVE if index == self.selected else BUTTON, button, border_radius=4)
            text = self.font.render(label, True, LABEL)
            screen.blit(text, text.get_rect(center=button.center))
        return rect
