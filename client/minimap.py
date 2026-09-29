"""A plan of the building: which rooms exist, and which one I am standing in.

It never shows another player. Not knowing where anybody is is the game, so
the map answers "where am I and what is left" and nothing else.
"""

from __future__ import annotations

from typing import Any

import pygame

from gamemap import GameMap

MARGIN = 12
COMPACT_WIDTH = 220
EXPANDED_WIDTH = 620
PADDING = 10
LEGEND_HEIGHT = 18

PANEL = (22, 24, 30, 225)
EDGE = (74, 78, 92)
ROOM = (54, 58, 70)
ROOM_VISITED = (86, 74, 54)
ROOM_HERE = (196, 168, 96)
STAIRS = (62, 74, 92)
ROOM_EDGE = (34, 36, 44)
DOT = (236, 238, 244)
LABEL = (206, 210, 220)
TITLE = (140, 146, 160)


class Minimap:
    def __init__(self, game_map: GameMap, font: pygame.font.Font, label_font: pygame.font.Font) -> None:
        self.map = game_map
        self.font = font
        self.label_font = label_font
        self.expanded = False
        self.visited: set[str] = set()

        rooms = game_map.rooms
        left = min(room["rect"][0] for room in rooms)
        top = min(room["rect"][1] for room in rooms)
        self.bounds = pygame.Rect(
            left,
            top,
            max(room["rect"][0] + room["rect"][2] for room in rooms) - left,
            max(room["rect"][1] + room["rect"][3] for room in rooms) - top,
        )

    def toggle(self) -> None:
        self.expanded = not self.expanded

    def note_visit(self, room_id: str | None) -> None:
        if room_id is not None:
            self.visited.add(room_id)

    def draw(
        self,
        screen: pygame.Surface,
        current_room: str | None,
        position: tuple[float, float] | None,
        show_visited: bool,
    ) -> None:
        width = EXPANDED_WIDTH if self.expanded else COMPACT_WIDTH
        scale = (width - PADDING * 2) / self.bounds.width
        height = round(self.bounds.height * scale) + PADDING * 2
        if not self.expanded:
            height += LEGEND_HEIGHT

        if self.expanded:
            origin = ((screen.get_width() - width) // 2, (screen.get_height() - height) // 2)
        else:
            origin = (screen.get_width() - width - MARGIN, MARGIN)
        panel = pygame.Rect(*origin, width, height)

        surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, PANEL, surface.get_rect(), border_radius=6)
        pygame.draw.rect(surface, EDGE, surface.get_rect(), width=1, border_radius=6)

        for room in self.map.rooms:
            rect = self._project(room["rect"], scale)
            if room["id"] == current_room:
                color = ROOM_HERE
            elif show_visited and room["id"] in self.visited:
                color = ROOM_VISITED
            elif room.get("stairs"):
                color = STAIRS
            else:
                color = ROOM
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, ROOM_EDGE, rect, width=1)

            if self.expanded and rect.width > 30:
                label = self.label_font.render(room["name"], True, LABEL)
                surface.blit(label, label.get_rect(center=rect.center))

        if position is not None:
            size = self.map.tile_size
            dot = (
                PADDING + (position[0] / size - self.bounds.x) * scale,
                PADDING + (position[1] / size - self.bounds.y) * scale,
            )
            pygame.draw.circle(surface, DOT, dot, 4 if self.expanded else 3)

        if not self.expanded:
            surface.blit(
                self.font.render("M  map", True, TITLE),
                (PADDING, height - LEGEND_HEIGHT),
            )

        screen.blit(surface, panel.topleft)

    def _project(self, rect: list[int], scale: float) -> pygame.Rect:
        x, y, w, h = rect
        return pygame.Rect(
            PADDING + round((x - self.bounds.x) * scale),
            PADDING + round((y - self.bounds.y) * scale),
            max(1, round(w * scale)),
            max(1, round(h * scale)),
        )
