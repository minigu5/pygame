"""Phase 0 client: connect to a room and show the round-trip time."""

from __future__ import annotations

import argparse
import sys
import time

import pygame

from net import Connection

WIDTH, HEIGHT = 960, 540
BACKGROUND = (24, 26, 32)
TEXT = (226, 228, 234)
DIM = (128, 132, 142)
PING_INTERVAL = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="ws://127.0.0.1:8787")
    parser.add_argument("--room", default="test")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    connection = Connection(f"{args.server}/ws?room={args.room}")
    connection.start()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Meccha Chameleon 2D")
    font = pygame.font.SysFont("menlo,monospace", 20)
    clock = pygame.time.Clock()

    player_id = "-"
    role = "-"
    rtt_ms: float | None = None
    peers: set[str] = set()
    next_ping = 0.0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        now = time.monotonic()
        if connection.status == "connected" and now >= next_ping:
            connection.send({"t": "ping", "ts": int(now * 1000)})
            next_ping = now + PING_INTERVAL

        for message in connection.poll():
            kind = message.get("t")
            if kind == "hello":
                player_id = message["id"]
                role = message["role"]
            elif kind == "pong":
                rtt_ms = now * 1000 - message["ts"]
            elif kind == "j":
                peers.add(message["id"])
            elif kind == "b":
                peers.discard(message["id"])

        lines = [
            f"server   {args.server}  room={args.room}",
            f"status   {connection.status}",
            f"id       {player_id}   role {role}",
            f"rtt      {'-' if rtt_ms is None else f'{rtt_ms:.0f} ms'}",
            f"peers    {len(peers)}",
        ]
        if connection.error:
            lines.append(f"error    {connection.error}")

        screen.fill(BACKGROUND)
        for index, line in enumerate(lines):
            color = TEXT if index < 5 else DIM
            screen.blit(font.render(line, True, color), (40, 40 + index * 28))
        pygame.display.flip()
        clock.tick(60)

    connection.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
