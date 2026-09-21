"""Client: sends input, draws whatever the server reports."""

from __future__ import annotations

import argparse
import sys
import time

import pygame

from gamemap import GameMap, load_tuning
from net import Connection
from playerinput import InputBatcher, sample
from render import Renderer

WIDTH, HEIGHT = 960, 540
PING_INTERVAL = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="ws://127.0.0.1:8787")
    parser.add_argument("--room", default="test")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tuning = load_tuning()

    connection = Connection(f"{args.server}/ws?room={args.room}")
    connection.start()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Meccha Chameleon 2D")
    clock = pygame.time.Clock()

    game_map = GameMap.load("map_test")
    renderer = Renderer(screen, game_map, tuning)
    batcher = InputBatcher(tuning["input_batch"])

    player_id = "-"
    role = "-"
    rtt_ms: float | None = None
    me: dict | None = None
    others: list[dict] = []
    next_ping = 0.0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        now = time.monotonic()
        if connection.status == "connected":
            message = batcher.push(sample())
            if message is not None:
                connection.send(message)
            if now >= next_ping:
                connection.send({"t": "ping", "ts": int(now * 1000)})
                next_ping = now + PING_INTERVAL

        for message in connection.poll():
            kind = message.get("t")
            if kind == "hello":
                player_id = message["id"]
                role = message["role"]
            elif kind == "pong":
                rtt_ms = now * 1000 - message["ts"]
            elif kind == "s":
                me = message["me"]
                others = message["o"]
            elif kind == "b":
                others = [o for o in others if o["i"] != message["id"]]

        if me is not None:
            renderer.follow(
                me["x"] + tuning["player_width"] / 2,
                me["y"] + tuning["player_height"] / 2,
            )

        status = [
            f"{role}  id {player_id}  {connection.status}",
            f"rtt {'-' if rtt_ms is None else f'{rtt_ms:.0f}ms'}  room {me['rm'] if me else '-'}",
            f"pos {me['x'] if me else '-'},{me['y'] if me else '-'}  peers {len(others)}",
        ]
        if connection.error:
            status.append(connection.error)

        renderer.draw(me, others, status)
        pygame.display.flip()
        clock.tick(60)

    connection.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
