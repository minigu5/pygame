"""The first screen: the rooms that are open, and a way into one or a new one."""

from __future__ import annotations

import json
import queue
import re
import secrets
import string
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import pygame

from fonts import has_korean, readable, ui_font
from keys import game_keys, latin_key
from ui_widgets import DIM, LABEL, PANEL_BG, PANEL_EDGE, TEXT, Button

BACKGROUND = (14, 15, 20)
ROW_SELECTED = (52, 70, 110)
ROW_HOVER = (38, 41, 52)
HEADER = (140, 146, 160)
OPEN = (132, 204, 150)
BUSY = (214, 178, 108)
NOTICE_BG = (92, 48, 44)
NOTICE_TEXT = (244, 214, 208)

MARGIN = 40
ROW_HEIGHT = 38
HEADER_HEIGHT = 34
COLUMNS = (("방 이름", 20), ("방 코드", 400), ("인원", 590), ("상태", 700))

REFRESH_SECONDS = 4.0
FETCH_TIMEOUT = 6.0
DOUBLE_CLICK_SECONDS = 0.4
# The server sits behind Cloudflare, which turns away urllib's own
# "Python-urllib/3.x" as a bot (HTTP 403, error 1010): the list would never load.
USER_AGENT = "meccha-chameleon-client/1.0"

ROOM_CODE = re.compile(r"^[a-z0-9-]{1,32}$")
CODE_ALPHABET = string.ascii_lowercase + string.digits
CODE_LENGTH = 6


class LobbyError(Exception):
    """Why the room list could not be read, in words for the player."""


@dataclass
class RoomChoice:
    code: str
    name: str | None = None     # set when this opens a new room

    def query(self) -> str:
        """The room part of the WebSocket address."""
        return f"room={self.code}" + (f"&name={quote(self.name)}" if self.name else "")


def http_base(server: str) -> str:
    """The server's HTTP address, from the WebSocket one the client is given."""
    for socket_scheme, http_scheme in (("wss://", "https://"), ("ws://", "http://")):
        if server.startswith(socket_scheme):
            return http_scheme + server[len(socket_scheme):].rstrip("/")
    return server.rstrip("/")


def fetch_rooms(server: str, timeout: float = FETCH_TIMEOUT) -> list[dict[str, Any]]:
    """The open rooms, each a dict of code, name, players, capacity and phase."""
    request = urllib.request.Request(
        http_base(server) + "/rooms",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            listed = json.load(response)
    except urllib.error.HTTPError as refused:
        raise LobbyError(f"서버가 요청을 받지 않았습니다. (HTTP {refused.code})") from refused
    except (OSError, ValueError) as failed:
        raise LobbyError("서버 주소와 네트워크를 확인하고 다시 시도하세요.") from failed
    if not isinstance(listed, list):
        raise LobbyError("서버가 알 수 없는 형식으로 답했습니다.")

    rooms = []
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        code, players, capacity = entry.get("code"), entry.get("players"), entry.get("capacity")
        if not (isinstance(code, str) and ROOM_CODE.match(code)):
            continue
        if not (isinstance(players, int) and isinstance(capacity, int)):
            continue
        name = entry.get("name")
        rooms.append(
            {
                "code": code,
                "name": name if isinstance(name, str) and name.strip() else code,
                "players": players,
                "capacity": capacity,
                "phase": str(entry.get("phase", "waiting")),
            }
        )
    # Rooms one can walk into first, those still waiting to start before those mid-round.
    rooms.sort(
        key=lambda room: (
            room["players"] >= room["capacity"],
            room["phase"] != "waiting",
            room["name"],
            room["code"],
        )
    )
    return rooms


def new_room_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class RoomList:
    """Reads the list on a thread of its own, so a slow server never freezes the screen."""

    def __init__(self, server: str) -> None:
        self.server = server
        self.rooms: list[dict[str, Any]] = []
        self.error: str | None = None
        self.loading = False
        self.loaded = False             # an answer, good or bad, has come back at least once
        self.next_refresh = 0.0
        self._results: queue.Queue[list[dict[str, Any]] | LobbyError] = queue.Queue()

    def refresh(self) -> None:
        if self.loading:
            return
        self.loading = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        try:
            self._results.put(fetch_rooms(self.server))
        except LobbyError as failed:
            self._results.put(failed)

    def poll(self) -> None:
        """Takes in a finished fetch and starts the next one when it is due."""
        try:
            result = self._results.get_nowait()
        except queue.Empty:
            if not self.loading and time.monotonic() >= self.next_refresh:
                self.refresh()
            return
        self.loading = False
        self.loaded = True
        self.next_refresh = time.monotonic() + REFRESH_SECONDS
        if isinstance(result, LobbyError):
            self.rooms, self.error = [], str(result)
        else:
            self.rooms, self.error = result, None


class Lobby:
    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        server: str,
        notice: str | None = None,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.server = server
        self.notice = notice            # why the last room was left, if not by choice
        self.list = RoomList(server)
        self.selected: str | None = None
        self.scroll = 0
        self.create = Button("새 방 만들기", primary=True)
        self.join = Button("입장")
        self.reload = Button("새로고침")
        self.quit = Button("종료")
        self._rows: list[tuple[pygame.Rect, dict[str, Any]]] = []
        self._last_click: tuple[float, str] = (0.0, "")

    def run(self) -> RoomChoice | None:
        """Shows the lobby until a room is chosen; None means the player quit."""
        game_keys()
        while True:
            self.list.poll()
            if self.selected is not None and self._room(self.selected) is None:
                self.selected = None
            for event in pygame.event.get():
                choice = self._on_event(event)
                if choice is not None:
                    return choice or None
            self._draw()
            pygame.display.flip()
            self.clock.tick(60)

    def _room(self, code: str | None) -> dict[str, Any] | None:
        return next((room for room in self.list.rooms if room["code"] == code), None)

    def _joinable(self, room: dict[str, Any] | None) -> bool:
        return room is not None and room["players"] < room["capacity"]

    def _new_room(self) -> RoomChoice:
        code = new_room_code()
        return RoomChoice(code, f"방 {code[:4]}" if has_korean() else f"room {code[:4]}")

    def _on_event(self, event: pygame.event.Event) -> RoomChoice | bool | None:
        """A RoomChoice to enter, False to quit, None to stay."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.WINDOWFOCUSGAINED:
            game_keys()     # the IME is shut out of the focused window, so once per focus
        elif event.type == pygame.KEYDOWN:
            key = latin_key(event)
            if key == pygame.K_ESCAPE:
                return False
            if key == pygame.K_n:
                return self._new_room()
            if key == pygame.K_r or key == pygame.K_F5:
                self.list.refresh()
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self._joinable(self._room(self.selected)):
                    return RoomChoice(self.selected)
            elif key in (pygame.K_UP, pygame.K_DOWN) and self.list.rooms:
                codes = [room["code"] for room in self.list.rooms]
                step = 1 if key == pygame.K_DOWN else -1
                index = codes.index(self.selected) + step if self.selected in codes else 0
                index = max(0, min(len(codes) - 1, index))
                self.selected = codes[index]
                visible = self._visible_rows()
                self.scroll = max(index - visible + 1, min(self.scroll, index))
        elif event.type == pygame.MOUSEWHEEL:
            limit = max(0, len(self.list.rooms) - self._visible_rows())
            self.scroll = max(0, min(limit, self.scroll - event.y))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.create.hit(event.pos):
                return self._new_room()
            if self.quit.hit(event.pos):
                return False
            if self.reload.hit(event.pos):
                self.list.refresh()
            elif self.join.hit(event.pos):
                return RoomChoice(self.selected)
            else:
                for rect, room in self._rows:
                    if rect.collidepoint(event.pos):
                        now = time.monotonic()
                        again = self._last_click[1] == room["code"] and now - self._last_click[0] < DOUBLE_CLICK_SECONDS
                        self._last_click = (now, room["code"])
                        self.selected = room["code"]
                        if again and self._joinable(room):
                            return RoomChoice(room["code"])
        return None

    def _list_rect(self) -> pygame.Rect:
        width, height = self.screen.get_size()
        return pygame.Rect(MARGIN, 104, width - MARGIN * 2, height - 104 - 108)

    def _visible_rows(self) -> int:
        return max(1, (self._list_rect().height - HEADER_HEIGHT - 8) // ROW_HEIGHT)

    def _draw(self) -> None:
        screen = self.screen
        width, height = screen.get_size()
        screen.fill(BACKGROUND)

        title = "메챠 카멜레온 2D" if has_korean() else "Meccha Chameleon 2D"
        screen.blit(ui_font(30).render(title, True, TEXT), (MARGIN, 28))
        server = ui_font(14).render(http_base(self.server).split("://")[-1], True, DIM)
        screen.blit(server, server.get_rect(bottomright=(width - MARGIN, 64)))
        if self.notice:
            note = ui_font(15).render(self.notice, True, NOTICE_TEXT)
            box = note.get_rect(midleft=(MARGIN + 320, 48)).inflate(24, 12)
            pygame.draw.rect(screen, NOTICE_BG, box, border_radius=6)
            screen.blit(note, note.get_rect(center=box.center))

        panel = self._list_rect()
        pygame.draw.rect(screen, PANEL_BG, panel, border_radius=8)
        pygame.draw.rect(screen, PANEL_EDGE, panel, width=1, border_radius=8)
        for label, offset in COLUMNS:
            screen.blit(ui_font(14).render(label, True, HEADER), (panel.x + offset, panel.y + 9))
        pygame.draw.line(
            screen, PANEL_EDGE, (panel.x + 1, panel.y + HEADER_HEIGHT), (panel.right - 2, panel.y + HEADER_HEIGHT)
        )

        self._rows = []
        rooms = self.list.rooms
        if rooms:
            self._draw_rows(panel, rooms)
        else:
            self._draw_empty(panel)

        y = height - 84
        self.create.draw(screen, pygame.Rect(MARGIN, y, 170, 44))
        self.join.enabled = self._joinable(self._room(self.selected))
        self.join.draw(screen, pygame.Rect(MARGIN + 182, y, 110, 44))
        self.reload.draw(screen, pygame.Rect(MARGIN + 304, y, 120, 44))
        self.quit.draw(screen, pygame.Rect(width - MARGIN - 100, y, 100, 44))

        if self.list.loading:
            busy = ui_font(13).render("불러오는 중…", True, DIM)
            screen.blit(busy, busy.get_rect(midleft=(MARGIN + 440, y + 22)))
        hint = "↑↓ 고르기 · Enter 입장 · N 새 방 · R 새로고침 · Esc 종료"
        screen.blit(ui_font(13).render(hint, True, DIM), (MARGIN, height - 30))

    def _draw_rows(self, panel: pygame.Rect, rooms: list[dict[str, Any]]) -> None:
        screen = self.screen
        visible = self._visible_rows()
        self.scroll = max(0, min(self.scroll, max(0, len(rooms) - visible)))
        mouse = pygame.mouse.get_pos()
        font = ui_font(16)
        top = panel.y + HEADER_HEIGHT + 4
        for index, room in enumerate(rooms[self.scroll : self.scroll + visible]):
            row = pygame.Rect(panel.x + 6, top + index * ROW_HEIGHT, panel.width - 12, ROW_HEIGHT - 2)
            self._rows.append((row, room))
            if room["code"] == self.selected:
                pygame.draw.rect(screen, ROW_SELECTED, row, border_radius=5)
            elif row.collidepoint(mouse):
                pygame.draw.rect(screen, ROW_HOVER, row, border_radius=5)

            full = room["players"] >= room["capacity"]
            waiting = room["phase"] == "waiting"
            status = "가득 참" if full else "대기 중" if waiting else "게임 중"
            cells = (
                (readable(room["name"]), TEXT),
                (room["code"], DIM),
                (f"{room['players']} / {room['capacity']}", LABEL),
                (status, DIM if full else OPEN if waiting else BUSY),
            )
            for (text, ink), (_, offset) in zip(cells, COLUMNS):
                label = font.render(text, True, ink)
                screen.blit(label, label.get_rect(midleft=(panel.x + offset, row.centery)))

        if len(rooms) > visible:
            more = ui_font(13).render(f"{self.scroll + 1}-{self.scroll + visible} / {len(rooms)}", True, DIM)
            screen.blit(more, more.get_rect(topright=(panel.right - 16, panel.y + 9)))

    def _draw_empty(self, panel: pygame.Rect) -> None:
        if self.list.error is not None:
            lines = (("방 목록을 불러오지 못했습니다.", TEXT), (self.list.error, DIM))
        elif not self.list.loaded:
            lines = (("방 목록을 불러오는 중…", DIM),)
        else:
            lines = (("열려 있는 방이 없습니다.", TEXT), ("새 방 만들기로 첫 방을 열어 보세요.", DIM))
        centre_y = panel.centery + HEADER_HEIGHT // 2 - (len(lines) - 1) * 14
        for index, (text, ink) in enumerate(lines):
            label = ui_font(18 if index == 0 else 15).render(text, True, ink)
            self.screen.blit(label, label.get_rect(center=(panel.centerx, centre_y + index * 30)))
