"""Run the real client headless against a server with scripted keys and check
it stays in step: a frozen body never moves on screen, the input backlog stays
small, and the camera's room follows the body into the next room.

This is main.py itself with the display, keys and clock stubbed, so it covers
the client loop, the predictor and the server together, the way a player sees
them. Two bugs it was written for: a freeze applied by the server many frames
late (the body jumped back to where the server still had it) and a camera
framing the room the server last reported rather than the one the body is in.

Run `npm run dev --prefix server` first, then:
    .venv/bin/python tools/check_client_sync.py [ws://127.0.0.1:8787]
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import pygame  # noqa: E402
from websockets.sync.client import connect  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787"
ROOM = f"sync-{int(time.time())}"

# A hunter must be in the room first so the client under test is the chameleon.
hunter = connect(f"{BASE}/ws?room={ROOM}&hide=60&seek=600", legacy=True)
hunter.recv()


def drain() -> None:
    try:
        while True:
            # The hunter opened the room, so it is the host: start the round
            # as soon as the client under test has joined.
            if '"t":"r"' in hunter.recv():
                hunter.send('{"t":"start"}')
    except Exception:
        pass


threading.Thread(target=drain, daemon=True).start()

sys.argv = ["main.py", "--server", BASE, "--room", ROOM]
import main as game  # noqa: E402
from playerinput import JUMP, RIGHT  # noqa: E402
from predict import Predictor  # noqa: E402
from render import Renderer  # noqa: E402

# The chameleon spawns in the kitchen; the route runs it through the pantry
# into the store, freezing once on the ground and once in the air.
SCRIPT: dict[int, int] = {}


def fill(start: int, end: int, mask: int) -> None:
    for frame in range(start, end):
        SCRIPT[frame] = mask


fill(0, 120, 0)
fill(120, 240, RIGHT)
fill(240, 330, 0)                # frozen on the ground
fill(330, 400, RIGHT)
fill(400, 412, RIGHT | JUMP)
fill(412, 540, 0)                # frozen mid-air from 418 to 520
fill(540, 700, RIGHT)
SPACE_AT = {240, 330, 418, 520}
FROZEN = [(240, 330), (418, 520)]
END = 700

state = {"frame": -1}
log: list[dict] = []
corrections: list[dict] = []
backlog = 0

real_get = pygame.event.get


def scripted_events() -> list[pygame.event.Event]:
    real_get()
    state["frame"] += 1
    frame = state["frame"]
    events = []
    if frame in SPACE_AT:
        events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=0))
    if frame >= END:
        events.append(pygame.event.Event(pygame.QUIT))
    return events


pygame.event.get = scripted_events
game.sample = lambda: SCRIPT.get(state["frame"], 0)

real_frame = Renderer.frame


def logged_frame(self: Renderer, room_id: str | None, focus_x: float, focus_y: float) -> None:
    real_frame(self, room_id, focus_x, focus_y)
    log.append({"frame": state["frame"], "room": room_id, "focus": (focus_x, focus_y), "camera": (self.camera.x, self.camera.y)})


Renderer.frame = logged_frame
real_reconcile = Predictor.reconcile


def logged_reconcile(self: Predictor, snapshot: dict, acked: int) -> None:
    global backlog
    before = (self.body.x, self.body.y) if self.body else None
    real_reconcile(self, snapshot, acked)
    backlog = max(backlog, len(self.history))
    if before and (abs(self.body.x - before[0]) > 1 or abs(self.body.y - before[1]) > 1):
        corrections.append({"frame": state["frame"], "dx": self.body.x - before[0], "dy": self.body.y - before[1]})


Predictor.reconcile = logged_reconcile

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


game.main()

moved_frozen = []
for previous, entry in zip(log, log[1:]):
    frame = entry["frame"]
    if any(start < frame < end for start, end in FROZEN) and previous["frame"] == frame - 1:
        dx = entry["focus"][0] - previous["focus"][0]
        dy = entry["focus"][1] - previous["focus"][1]
        if abs(dx) > 1 or abs(dy) > 1:
            moved_frozen.append((frame, round(dx, 1), round(dy, 1)))
check("a frozen body stays put on screen", not moved_frozen, f"{moved_frozen[:4]}" if moved_frozen else "")
big = [c for c in corrections if abs(c["dx"]) > 8 or abs(c["dy"]) > 8]
check("no correction larger than 8px", not big, f"{[(c['frame'], round(c['dx']), round(c['dy'])) for c in big[:4]]}" if big else f"{len(corrections)} small ones")
check("input backlog stays under a snapshot's worth", backlog <= 12, f"peak {backlog} frames")
rooms = []
for entry in log:
    if entry["room"] is not None and (not rooms or rooms[-1] != entry["room"]):
        rooms.append(entry["room"])
check("the camera's room follows the body", rooms == ["1F-kitchen", "1F-pantry", "1F-store"], f"{rooms}")
last = log[-1]
check("the camera ends up framing the store", abs(last["camera"][0] - (2240 + 320 - 480)) < 200, f"camera x {last['camera'][0]:.0f} body x {last['focus'][0]:.0f}")

print()
print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
sys.exit(0 if not failures else 1)
