"""Client: sends input, draws whatever the server reports."""

from __future__ import annotations

import argparse
import sys
import time

import pygame

from gamemap import GameMap, load_tuning
from net import Connection
from physics import Physics
from playerinput import InputBatcher, sample
from predict import Interpolator, Predictor
from render import Renderer
from ui_paint import PaintPanel, sample_map_color

WIDTH, HEIGHT = 960, 540
PING_INTERVAL = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="wss://chameleon.omm.run")
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
    physics = Physics(game_map, tuning)
    predictor = Predictor(physics, 1000 / tuning["tick_hz"])
    interpolator = Interpolator(1000 / tuning["snapshot_hz"])
    panel = PaintPanel(pygame.font.SysFont("menlo,monospace", 14), (210, 120, 90))
    frozen = False
    caught = False
    cooldown_until = 0.0

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
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_TAB and role == "chameleon":
                frozen = not frozen
                connection.send({"t": "f", "v": frozen})
                if predictor.body is not None:
                    predictor.body.frozen = frozen
                if not frozen:
                    panel.eyedropper = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_e and frozen:
                panel.toggle_eyedropper()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and frozen:
                if not panel.on_mouse_down(event.pos):
                    if panel.eyedropper:
                        picked = sample_map_color(game_map, *renderer.to_world(*event.pos))
                        if picked is not None:
                            panel.set_color(picked)
            elif (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and role == "hunter"
                and time.monotonic() >= cooldown_until
            ):
                world_x, world_y = renderer.to_world(*event.pos)
                connection.send({"t": "a", "x": world_x, "y": world_y})
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                panel.on_mouse_up()
            elif event.type == pygame.MOUSEMOTION:
                panel.on_mouse_move(event.pos)

        now = time.monotonic()
        if connection.status == "connected":
            mask = 0 if frozen else sample()
            frame, message = batcher.push(mask)
            predictor.record(frame, mask)
            predictor.advance(mask)
            if message is not None:
                connection.send(message)
            if now >= next_ping:
                connection.send({"t": "ping", "ts": int(now * 1000)})
                next_ping = now + PING_INTERVAL
            changed = panel.take_change()
            if changed is not None:
                connection.send({"t": "p", "c": list(changed)})

        for message in connection.poll():
            kind = message.get("t")
            if kind == "hello":
                player_id = message["id"]
                role = message["role"]
            elif kind == "pong":
                rtt_ms = now * 1000 - message["ts"]
            elif kind == "s":
                me = message["me"]
                predictor.reconcile(me, message["n"])
                interpolator.push(message["o"])
            elif kind == "b":
                interpolator.drop(message["id"])
            elif kind == "c":
                interpolator.drop(message["id"])
                if message["id"] == player_id:
                    caught = True
                    role = "spectator"
                    frozen = False
            elif kind == "cd":
                # The server's timestamp is wall clock; only the length matters.
                cooldown_until = now + tuning["accuse_cooldown_ms"] / 1000

        others = interpolator.at_now()
        drawn_me = None
        if me is not None:
            if caught:
                # Watching through a hunter's eyes: no prediction of my own.
                x, y = float(me["x"]), float(me["y"])
            else:
                x, y = predictor.render_position()
            drawn_me = {"x": x, "y": y, "c": panel.color if role == "chameleon" else me["c"]}
            renderer.frame(
                me["rm"],
                x + tuning["player_width"] / 2,
                y + tuning["player_height"] / 2,
            )

        remaining = max(0.0, cooldown_until - now)
        status = [
            f"{role}  id {player_id}  {connection.status}"
            + ("  CAUGHT - spectating" if caught else ""),
            f"rtt {'-' if rtt_ms is None else f'{rtt_ms:.0f}ms'}  room {me['rm'] if me else '-'}"
            + ("  FROZEN" if frozen else ""),
            f"pos {drawn_me['x']:.0f},{drawn_me['y']:.0f}" if drawn_me else "pos -",
            f"unacked {len(predictor.history)}  peers {len(others)}"
            + (f"  accuse in {remaining:.1f}s" if remaining > 0 else ""),
        ]
        if connection.error:
            status.append(connection.error)

        renderer.draw(me["rm"] if me else None, drawn_me, others, status)
        if frozen:
            panel.draw(screen)
        pygame.display.flip()
        clock.tick(60)

    connection.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
