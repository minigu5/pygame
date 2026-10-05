"""Client: sends input, draws whatever the server reports."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import pygame

import body_shape
from audio import Audio
from body_canvas import BodyCanvas
from body_shape import POSE_LABELS, POSES
from fonts import has_korean, ui_font
from gait import Gait
from gamemap import GameMap, load_tuning
from hud import Hud
from keys import game_keys, latin_key
from lobby import Lobby
from minimap import Minimap
from net import Connection
from physics import Physics
from playerinput import InputBatcher, sample, sample_frozen
from predict import Interpolator, Predictor
from render import Renderer
from ui_bar import ButtonBar
from ui_brush import Brush, PaintTarget
from ui_paint import PaintPanel, sample_map_color
from ui_widgets import Dialog
from waiting import WaitingRoom

WIDTH, HEIGHT = 960, 540
PING_INTERVAL = 1.0
MAX_ZOOM = 16.0
ZOOM_STEP = 1.25
BODY_COLOR = (210, 120, 90)
WALK_MIN_SPEED = 30.0   # px/s; slower than this on the ground is standing, not stepping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="wss://chameleon.omm.run")
    parser.add_argument("--room", default=None, help="join this room straight away, skipping the lobby")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tuning = load_tuning()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Meccha Chameleon 2D")
    clock = pygame.time.Clock()
    game_keys()

    game_map = GameMap.load("map_01")
    audio = Audio()

    # Lobby, room, lobby, room... until the player quits from either.
    query = f"room={args.room}" if args.room else None
    notice: str | None = None
    while True:
        if query is None:
            choice = Lobby(screen, clock, args.server, notice).run()
            if choice is None:
                break
            query = choice.query()
        outcome, notice = play(screen, clock, f"{args.server}/ws?{query}", game_map, tuning, audio)
        if outcome == "quit":
            break
        query = None

    pygame.quit()
    return 0


def play(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    url: str,
    game_map: GameMap,
    tuning: dict[str, Any],
    audio: Audio,
) -> tuple[str, str | None]:
    """One stay in a room, from connecting to leaving it. Returns "lobby" or
    "quit", and what to tell the player if the stay was cut short."""
    connection = Connection(url)
    connection.start()
    game_keys()

    renderer = Renderer(screen, game_map, tuning)
    batcher = InputBatcher(tuning["input_batch"])
    physics = Physics(game_map, tuning)
    predictor = Predictor(physics, 1000 / tuning["tick_hz"])
    interpolator = Interpolator(1000 / tuning["snapshot_hz"])
    panel = PaintPanel(ui_font(14), BODY_COLOR)
    canvas = BodyCanvas(BODY_COLOR)
    # Without any Korean font the labels would all be the same empty boxes.
    ascii_labels = not has_korean()
    brush = Brush(ui_font(14), canvas, ascii_labels)
    pose_labels = body_shape.POSE_LABELS_ASCII if ascii_labels else POSE_LABELS
    pose_bar = ButtonBar(ui_font(14), [pose_labels[pose] for pose in POSES])
    body_target: PaintTarget | None = None
    minimap = Minimap(game_map, ui_font(12), ui_font(13))
    hud = Hud()
    waiting = WaitingRoom(tuning["room_limits"])
    menu: Dialog | None = None      # the Esc menu, while it is up
    gait = Gait()
    frozen = False
    caught = False
    cooldown_until = 0.0
    phase = "waiting"
    seconds_left = 0
    round_number = 0
    winner: str | None = None

    player_id = "-"
    role = "-"
    rtt_ms: float | None = None
    me: dict | None = None
    room_id: str | None = None   # the room the camera frames, from where I am drawn
    others: list[dict] = []
    next_ping = 0.0

    def paint_target(pos: tuple[int, int]) -> PaintTarget | None:
        """The body as drawn when the brush may paint at pos, else None:
        not while picking colours, dragging a slider or over the panels."""
        if (
            not frozen
            or panel.eyedropper
            or panel.dragging is not None
            or panel.layout(screen).collidepoint(pos)
            or brush.bar.contains(pos)
            or pose_bar.contains(pos)
        ):
            return None
        return body_target

    def stand_up() -> None:
        """Back to attention: the pose is only held while frozen."""
        pose_bar.selected = 0

    def put_down_tools() -> None:
        """Out of freeze mode on this side: brush up, palette shut, camera back."""
        nonlocal frozen
        frozen = False
        panel.eyedropper = False
        panel.on_mouse_up()
        brush.release()
        renderer.zoom = 1.0
        stand_up()

    outcome: str | None = None
    notice: str | None = None
    while outcome is None:
        for event in pygame.event.get():
            # The key as a letter whichever way the 한/영 key is set: see keys.py.
            key = latin_key(event) if event.type == pygame.KEYDOWN else None
            if event.type == pygame.WINDOWFOCUSGAINED and not waiting.name.focused:
                game_keys()     # the IME is shut out of the focused window, so once per focus
            if event.type == pygame.QUIT:
                outcome = "quit"
            elif menu is not None:
                if key == pygame.K_ESCAPE:
                    menu = None
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    picked = menu.choice_at(event.pos)
                    if picked == "resume":
                        menu = None
                    elif picked is not None:
                        outcome = picked
            elif phase == "waiting" and waiting.on_event(event, player_id):
                pass
            elif key == pygame.K_ESCAPE:
                # Leaving is a choice, not an accident: ask first. The game
                # does not stop behind the menu, so the brush is lifted.
                panel.on_mouse_up()
                brush.release()
                menu = Dialog(
                    "메뉴",
                    "방을 나가면 처음 화면으로 돌아갑니다.",
                    [("resume", "계속하기"), ("lobby", "방 나가기"), ("quit", "게임 종료")],
                )
            elif key == pygame.K_SPACE and role == "chameleon" and not caught:
                frozen = not frozen
                audio.play("freeze")
                # Stamped with the next input frame, so the server freezes the
                # body exactly where this frame's prediction does.
                connection.send({"t": "f", "v": frozen, "n": batcher.frame + 1})
                if predictor.body is not None:
                    predictor.body.frozen = frozen
                if not frozen:
                    put_down_tools()
            elif key == pygame.K_z and event.mod & pygame.KMOD_CTRL and frozen:
                canvas.undo()
            elif key is not None and frozen and brush.bar.select_key(key):
                panel.eyedropper = False
            elif key in (pygame.K_UP, pygame.K_DOWN) and frozen:
                # Down goes from standing to crouching to lying; up comes back.
                step = 1 if key == pygame.K_DOWN else -1
                pose_bar.selected = max(0, min(len(POSES) - 1, pose_bar.selected + step))
                # The body is a different shape now: no painting through the
                # old outline until the next frame draws the new one.
                body_target = None
            elif event.type == pygame.MOUSEWHEEL and frozen:
                renderer.zoom = max(1.0, min(MAX_ZOOM, renderer.zoom * ZOOM_STEP**event.y))
                brush.lift()
            elif key == pygame.K_m:
                minimap.toggle()
            elif key == pygame.K_n:
                audio.toggle()
            elif key == pygame.K_e and frozen:
                panel.toggle_eyedropper()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and frozen:
                if brush.bar.on_mouse_down(event.pos):
                    panel.eyedropper = False
                elif pose_bar.on_mouse_down(event.pos):
                    body_target = None
                elif not panel.on_mouse_down(event.pos):
                    if panel.eyedropper:
                        picked = sample_map_color(game_map, *renderer.to_world(*event.pos))
                        if picked is not None:
                            panel.set_color(picked)
                            audio.play("pick")
                    else:
                        brush.press(event.pos, paint_target(event.pos), panel.color)
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
                brush.release()
            elif event.type == pygame.MOUSEMOTION:
                panel.on_mouse_move(event.pos)
                brush.move(event.pos, paint_target(event.pos), panel.color)

        for message in waiting.outbox:
            connection.send(message)
        waiting.outbox.clear()
        if waiting.leaving and outcome is None:
            outcome = "lobby"

        audio.paint(brush.take_stamped())
        now = time.monotonic()
        if connection.status == "connected":
            # Only a body the server is moving has input to send. In the
            # waiting room, watching, or caught, the server acknowledges no
            # frames, and the unacknowledged ones would pile up for as long
            # as the wait lasts, each snapshot replaying all of them.
            if role in ("hunter", "chameleon") and phase != "waiting" and not caught:
                blind = phase == "hiding" and role == "hunter"
                idle = blind or phase == "result" or menu is not None
                # Frozen keys slide the pinned body instead of walking it.
                mask = 0 if idle else sample_frozen() if frozen else sample()
                frame, message = batcher.push(mask)
                predictor.step(frame, mask)
                if message is not None:
                    connection.send(message)
            if now >= next_ping:
                connection.send({"t": "ping", "ts": int(now * 1000)})
                next_ping = now + PING_INTERVAL
            changed = panel.take_change()
            if changed is not None:
                connection.send({"t": "p", "c": list(changed)})
        elif connection.ended and outcome is None:
            # Refused at the door or cut off in the middle: either way the
            # lobby is where to go, with the reason on show there.
            outcome, notice = "lobby", connection.error

        for message in connection.poll():
            kind = message.get("t")
            if kind == "hello":
                player_id = message["id"]
                # Newer servers leave the role to the first snapshot.
                role = message.get("role", role)
            elif kind == "pong":
                rtt_ms = now * 1000 - message["ts"]
            elif kind == "r":
                waiting.update(message)
            elif kind == "s":
                me = message["me"]
                if message["ph"] != phase:
                    audio.play({"hiding": "hide", "seeking": "seek", "result": "result"}.get(message["ph"], ""))
                    waiting.close()
                if message["rd"] != round_number or (message["ph"] == "waiting" and phase != "waiting"):
                    # New round, or the round fell through and everyone is back
                    # in the waiting room: roles are dealt again and nothing
                    # carries over.
                    round_number = message["rd"]
                    put_down_tools()
                    minimap.visited.clear()
                    predictor.reset()
                    gait.clear()
                phase = message["ph"]
                seconds_left = message["left"]
                winner = message.get("win")
                role = me["rl"]
                caught = me["ct"]
                minimap.note_visit(me["rm"])
                predictor.reconcile(me, message["n"])
                interpolator.push(message["o"])
            elif kind == "b":
                interpolator.drop(message["id"])
                gait.forget(message["id"])
            elif kind == "c":
                interpolator.drop(message["id"])
                gait.forget(message["id"])
                audio.play("caught")
                if message["id"] == player_id:
                    put_down_tools()
            elif kind == "cd":
                audio.play("miss")
                # The server's timestamp is wall clock; only the length matters.
                cooldown_until = now + tuning["accuse_cooldown_ms"] / 1000

        others = interpolator.at_now()
        for other in others:
            # A frozen body that moves is being slid into place, not walking.
            other["frame"] = gait.frame(other["i"], other["x"], other["y"], False if other["fz"] else None)
            other["facing"] = gait.facing(other["i"])
        drawn_me = None
        body_target = None
        pose = POSES[pose_bar.selected] if frozen else "stand"
        if me is not None:
            if caught:
                # Watching through a hunter's eyes: no prediction of my own,
                # and their stride is read off their motion like anyone else's.
                x, y = float(me["x"]), float(me["y"])
                walking, direction = None, 0
            else:
                x, y = predictor.render_position()
                body = predictor.body
                walking = (
                    body is not None
                    and body.on_ground
                    and not body.frozen
                    and abs(body.vx) >= WALK_MIN_SPEED
                )
                direction = 0 if body is None or abs(body.vx) < WALK_MIN_SPEED else (1 if body.vx > 0 else -1)
            walk_frame = gait.frame("me", x, y, walking, direction) if pose == "stand" else None
            drawn_pose = "walk" if walk_frame is not None else pose
            painted = role == "chameleon" and not caught
            if not painted:
                sprite = body_shape.solid_sprite(me["c"], drawn_pose, walk_frame or 0)
            elif drawn_pose == "stand":
                sprite = body_shape.sprite(canvas.surface, pose)
            else:
                # Other poses show cells the standing figure hides.
                sprite = body_shape.sprite(canvas.extended(), drawn_pose, walk_frame or 0)
            if walk_frame is not None and gait.facing("me") < 0:
                sprite = pygame.transform.flip(sprite, True, False)
            drawn_me = {"x": x, "y": y, "pose": drawn_pose, "sprite": sprite}
            # The camera frames the room the drawn body is in, not the one the
            # server last reported: that is a round trip behind, so the body
            # would run out of the picture before the camera followed. In a
            # doorway between rooms it keeps the room it came from.
            if caught:
                room_id = me["rm"]
            else:
                here = game_map.room_at(x + tuning["player_width"] / 2, y + tuning["player_height"] / 2)
                room_id = here if here is not None else room_id
            # Zoomed in to paint, centre on the figure itself; a lying body
            # would otherwise run under the palette.
            focus = (
                body_shape.pose_rect(pose, x, y, tuning["player_width"], tuning["player_height"]).center
                if frozen
                else (x + tuning["player_width"] / 2, y + tuning["player_height"] / 2)
            )
            renderer.frame(room_id, *focus)
            if frozen and painted:
                body_target = PaintTarget(renderer.body_rect(pose, x, y), pose)

        remaining = max(0.0, cooldown_until - now)
        status = [
            f"{role}  id {player_id}  {connection.status}"
            + ("  CAUGHT - spectating" if caught else ""),
            f"rtt {'-' if rtt_ms is None else f'{rtt_ms:.0f}ms'}  room {me['rm'] or '-' if me else '-'}"
            + ("  FROZEN" if frozen else ""),
            f"pos {drawn_me['x']:.0f},{drawn_me['y']:.0f}" if drawn_me else "pos -",
            f"unacked {len(predictor.history)}  peers {len(others)}"
            + (f"  accuse in {remaining:.1f}s" if remaining > 0 else ""),
        ]

        renderer.draw(room_id, drawn_me, others, status)
        if not panel.eyedropper:
            brush.draw_cursor(screen, body_target)
        hud.draw(
            screen,
            phase,
            seconds_left,
            round_number,
            winner,
            blind=phase == "hiding" and role == "hunter",
            watching=role == "spectator",
            connecting=me is None,
        )
        minimap.draw(
            screen,
            room_id,
            (
                (drawn_me["x"] + tuning["player_width"] / 2, drawn_me["y"] + tuning["player_height"] / 2)
                if drawn_me
                else None
            ),
            show_visited=role == "hunter",
        )
        if frozen:
            panel.draw(screen)
            brush_bar = brush.bar.draw_above(screen, panel.layout(screen))
            pose_bar.draw_above(screen, brush_bar)
        if phase == "waiting" and me is not None:
            waiting.draw(screen, player_id)
        if menu is not None:
            menu.draw(screen)
        pygame.display.flip()
        clock.tick(60)

    waiting.close()
    audio.hush()
    # Wait a moment for the socket to close, so the room hears of the leaving
    # before the lobby next asks who is in it.
    connection.close(wait=1.0)
    return outcome, notice


if __name__ == "__main__":
    sys.exit(main())
