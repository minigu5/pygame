"""Round banner, the hunter's blindfold, and the result screen."""

from __future__ import annotations

import pygame

KOREAN_FONTS = "applesdgothicneo,applegothic,malgungothic,notosanskr,arialunicode"

PHASE_NAMES = {
    "waiting": "대기 중",
    "hiding": "숨는 시간",
    "seeking": "찾는 시간",
    "result": "결과",
}
WINNERS = {"hunter": "헌터 승리", "chameleons": "카멜레온 승리"}

BANNER_BG = (18, 20, 26, 220)
BANNER_EDGE = (78, 82, 96)
TEXT = (232, 234, 240)
DIM = (150, 155, 168)
BLIND = (10, 11, 15, 238)


class Hud:
    def __init__(self) -> None:
        self.banner_font = pygame.font.SysFont(KOREAN_FONTS, 18)
        self.big_font = pygame.font.SysFont(KOREAN_FONTS, 34)
        self.small_font = pygame.font.SysFont(KOREAN_FONTS, 15)

    def draw(
        self,
        screen: pygame.Surface,
        phase: str,
        seconds_left: int,
        round_number: int,
        winner: str | None,
        blind: bool,
    ) -> None:
        if phase == "waiting":
            self._centre_notice(screen, "다른 플레이어를 기다리는 중", "두 명이 모이면 시작한다")
            return

        self._banner(screen, phase, seconds_left, round_number)

        if winner is not None and phase == "result":
            self._centre_notice(
                screen, WINNERS.get(winner, winner), f"{seconds_left}초 뒤 역할을 바꿔 다음 판"
            )
        elif blind:
            self._centre_notice(
                screen, "카멜레온이 숨는 중", f"{seconds_left}초 뒤 찾기 시작", cover=True
            )

    def _banner(self, screen: pygame.Surface, phase: str, seconds_left: int, round_number: int) -> None:
        text = f"{round_number}라운드 · {PHASE_NAMES.get(phase, phase)} · {seconds_left}초"
        label = self.banner_font.render(text, True, TEXT)
        box = label.get_rect()
        box.inflate_ip(28, 14)
        box.midtop = (screen.get_width() // 2, 10)

        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, BANNER_BG, panel.get_rect(), border_radius=6)
        pygame.draw.rect(panel, BANNER_EDGE, panel.get_rect(), width=1, border_radius=6)
        screen.blit(panel, box.topleft)
        screen.blit(label, label.get_rect(center=box.center))

    def _centre_notice(
        self, screen: pygame.Surface, title: str, detail: str, cover: bool = False
    ) -> None:
        if cover:
            veil = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            veil.fill(BLIND)
            screen.blit(veil, (0, 0))

        heading = self.big_font.render(title, True, TEXT)
        subtitle = self.small_font.render(detail, True, DIM)
        centre_x = screen.get_width() // 2
        centre_y = screen.get_height() // 2
        screen.blit(heading, heading.get_rect(center=(centre_x, centre_y - 14)))
        screen.blit(subtitle, subtitle.get_rect(center=(centre_x, centre_y + 22)))
