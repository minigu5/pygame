"""The waiting room: who is here, how the room is set up, and the start button.

The server's "r" message is the room's word on all of it; this panel shows it
and, for the host, turns clicks into "cfg" and "start" messages. A guest sees
the same settings but cannot touch them.
"""

from __future__ import annotations

from typing import Any

import pygame

from fonts import readable, ui_font
from ui_widgets import DIM, LABEL, PANEL_EDGE, TEXT, Button, TextField

PANEL_FILL = (22, 24, 30, 236)
PANEL_WIDTH = 470
ROW_HEIGHT = 42
STEP_SIZE = 30

# (message field, label, unit, step, which limit in tuning.room_limits)
SETTINGS = (
    ("max", "최대 인원", "명", 1, "players"),
    ("hide", "숨는 시간", "초", 5, "hide"),
    ("seek", "찾는 시간", "초", 10, "seek"),
    ("result", "결과 표시", "초", 1, "result"),
)


class WaitingRoom:
    def __init__(self, limits: dict[str, Any]) -> None:
        self.limits = limits
        self.info: dict[str, Any] | None = None     # the server's last "r" message
        self.outbox: list[dict[str, Any]] = []      # messages for the server
        self.leaving = False                        # the leave button was pressed
        self.name = TextField(int(limits["name"]))
        self.start = Button("게임 시작", primary=True)
        self.leave = Button("방 나가기")
        self._steppers = {field: (Button("", sign=-1), Button("", sign=1)) for field, *_ in SETTINGS}

    def update(self, info: dict[str, Any]) -> None:
        self.info = {**info, "name": readable(str(info.get("name", "")))}

    def close(self) -> None:
        """The round started or the room was left: stop typing."""
        self.name.blur()

    def _is_host(self, player_id: str) -> bool:
        return self.info is not None and self.info.get("host") == player_id

    def _bounds(self, field: str, limit: str) -> tuple[int, int]:
        low, high = self.limits[limit]
        if field == "max" and self.info is not None:
            low = max(low, self.info["n"])      # cannot shut out someone already here
        return low, high

    def _commit_name(self) -> None:
        wanted = " ".join(self.name.text.split())
        self.name.blur()
        if self.info is not None and wanted and wanted != self.info["name"]:
            self.info["name"] = wanted
            self.outbox.append({"t": "cfg", "name": wanted})

    def on_event(self, event: pygame.event.Event, player_id: str) -> bool:
        """True when the event was the waiting room's and the game should not see it."""
        typed = self.name.on_event(event)
        if typed is not None:
            if typed == "commit":
                self._commit_name()
            elif typed == "cancel":
                self.name.blur()
            return True

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        if self.name.focused:
            self._commit_name()     # a click anywhere else ends the typing
        if self.leave.hit(event.pos):
            self.leaving = True
            return True
        if self.info is None or not self._is_host(player_id):
            return False
        if self.start.hit(event.pos):
            self.outbox.append({"t": "start"})
            return True
        if self.name.rect.collidepoint(event.pos):
            self.name.focus(self.info["name"])
            return True
        for field, _, _, step, limit in SETTINGS:
            low, high = self._bounds(field, limit)
            minus, plus = self._steppers[field]
            for button, change in ((minus, -step), (plus, step)):
                if button.hit(event.pos):
                    value = max(low, min(high, self.info[field] + change))
                    # Shown at once; the server's answer is the last word.
                    self.info[field] = value
                    self.outbox.append({"t": "cfg", field: value})
                    return True
        return False

    def draw(self, screen: pygame.Surface, player_id: str) -> None:
        info = self.info
        host = self._is_host(player_id)
        rows = len(SETTINGS) + 1 if info is not None else 0
        height = 86 + rows * ROW_HEIGHT + 110
        box = pygame.Rect(0, 0, PANEL_WIDTH, height)
        box.center = screen.get_rect().center
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, PANEL_FILL, panel.get_rect(), border_radius=10)
        pygame.draw.rect(panel, PANEL_EDGE, panel.get_rect(), width=1, border_radius=10)
        screen.blit(panel, box.topleft)

        left, right = box.x + 28, box.right - 28
        screen.blit(ui_font(24).render("대기실", True, TEXT), (left, box.y + 22))
        if info is not None:
            code = ui_font(14).render(f"방 코드 {info['code']}  ·  {'방장' if host else '참가자'}", True, DIM)
            screen.blit(code, code.get_rect(bottomright=(right, box.y + 52)))
        pygame.draw.line(screen, PANEL_EDGE, (left, box.y + 68), (right, box.y + 68))

        y = box.y + 86
        if info is not None:
            self._draw_settings(screen, info, host, left, right, y)
            y += rows * ROW_HEIGHT

        if info is None:
            notice = "다른 플레이어를 기다리는 중"
        elif info["n"] < 2:
            notice = f"지금 {info['n']}명 · 두 명 이상 모이면 시작할 수 있습니다"
        elif host:
            notice = f"지금 {info['n']}명 · 준비되면 게임 시작을 누르세요"
        else:
            notice = f"지금 {info['n']}명 · 방장이 시작하기를 기다리는 중"
        label = ui_font(15).render(notice, True, LABEL)
        screen.blit(label, label.get_rect(midtop=(box.centerx, y + 8)))

        buttons_y = box.bottom - 64
        if host:
            self.start.enabled = info is not None and info["n"] >= 2
            self.start.draw(screen, pygame.Rect(left, buttons_y, 250, 42))
            self.leave.draw(screen, pygame.Rect(right - 140, buttons_y, 140, 42))
        else:
            self.start.rect = pygame.Rect(0, 0, 0, 0)
            self.leave.draw(screen, pygame.Rect(box.centerx - 80, buttons_y, 160, 42))

    def _draw_settings(
        self, screen: pygame.Surface, info: dict[str, Any], host: bool, left: int, right: int, top: int
    ) -> None:
        font = ui_font(16)
        value_x = left + 250        # settings' values are centred on this line

        centre_y = top + ROW_HEIGHT // 2 - 4
        label = font.render("방 이름", True, DIM)
        screen.blit(label, label.get_rect(midleft=(left, centre_y)))
        field = pygame.Rect(left + 110, centre_y - 16, right - left - 110, 32)
        if host:
            if not self.name.focused:
                self.name.text = info["name"]
            self.name.draw(screen, field)
        else:
            self.name.rect = pygame.Rect(0, 0, 0, 0)
            name = font.render(info["name"], True, TEXT)
            screen.blit(name, name.get_rect(midleft=(field.x + 8, centre_y)))

        for index, (key, title, unit, _, limit) in enumerate(SETTINGS, start=1):
            centre_y = top + index * ROW_HEIGHT + ROW_HEIGHT // 2 - 4
            label = font.render(title, True, DIM)
            screen.blit(label, label.get_rect(midleft=(left, centre_y)))
            value = font.render(f"{info[key]}{unit}", True, TEXT)
            screen.blit(value, value.get_rect(center=(value_x, centre_y)))

            minus, plus = self._steppers[key]
            if not host:
                minus.rect = plus.rect = pygame.Rect(0, 0, 0, 0)
                continue
            low, high = self._bounds(key, limit)
            minus.enabled = info[key] > low
            plus.enabled = info[key] < high
            minus.draw(screen, pygame.Rect(value_x - 70 - STEP_SIZE, centre_y - STEP_SIZE // 2, STEP_SIZE, STEP_SIZE))
            plus.draw(screen, pygame.Rect(value_x + 70, centre_y - STEP_SIZE // 2, STEP_SIZE, STEP_SIZE))
