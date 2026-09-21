"""Replay one input sequence on the server and in the client's predictor.

The client predicts its own movement with a copy of the server's step
function. If the two drift the player sees constant rubber-banding, so this
runs the same frames through both and compares the result.

Run `npm run dev --prefix server` first, then:
    .venv/bin/python tools/check_physics_parity.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from websockets.asyncio.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from gamemap import GameMap, load_tuning  # noqa: E402
from physics import Body, Physics  # noqa: E402

RIGHT, JUMP = 2, 4
BATCH = 4
TOLERANCE_PX = 1.0

FRAMES = [RIGHT] * 90 + [RIGHT | JUMP] * 20 + [JUMP] * 10 + [0] * 120


async def run_on_server(base: str) -> dict:
    async with connect(f"{base}/ws?room=parity-{id(FRAMES)}") as socket:
        hello = json.loads(await socket.recv())
        assert hello["role"] == "hunter", hello

        # Send every frame up front so the queue never empties and the server
        # never falls back to coasting on the last mask.
        for start in range(0, len(FRAMES), BATCH):
            await socket.send(
                json.dumps({"t": "i", "n": start + 1, "k": FRAMES[start : start + BATCH]})
            )

        await asyncio.sleep(len(FRAMES) / 60 + 1.0)

        newest = None
        while True:
            try:
                message = json.loads(await asyncio.wait_for(socket.recv(), 0.2))
            except (TimeoutError, asyncio.TimeoutError):
                break
            if message.get("t") == "s":
                newest = message["me"]
        assert newest is not None, "no snapshot received"
        return newest


def run_locally(game_map: GameMap, tuning: dict) -> Body:
    physics = Physics(game_map, tuning)
    spawn = game_map.spawn["hunter"]
    body = Body(x=float(spawn[0]), y=float(spawn[1]))
    for mask in FRAMES:
        physics.step(body, mask, 1000 / tuning["tick_hz"])
    return body


async def main(base: str) -> int:
    tuning = load_tuning()
    game_map = GameMap.load("map_test")

    server = await run_on_server(base)
    local = run_locally(game_map, tuning)

    dx = abs(server["x"] - local.x)
    dy = abs(server["y"] - local.y)
    ok = dx <= TOLERANCE_PX and dy <= TOLERANCE_PX

    print(f"server  x={server['x']:.1f} y={server['y']:.1f} grounded={server['g']}")
    print(f"client  x={local.x:.1f} y={local.y:.1f} grounded={local.on_ground}")
    print(f"delta   dx={dx:.2f} dy={dy:.2f}  tolerance {TOLERANCE_PX}px")
    print("PASS  client prediction matches the server" if ok else "FAIL  physics drifted")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787")))
